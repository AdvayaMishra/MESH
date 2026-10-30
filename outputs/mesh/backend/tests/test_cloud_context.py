from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app import cloud_context as context
from app.auth import Principal
from app.cloud import AWSAssessment
from app.cloud_context_schema import Snapshot, Times, freshness
from app.cloud_identity import AWSAccountIdentity
from app.cloud_normalizer import CloudNormalizer
from app.cloud_publication import Report, assessment_record
from app.cloud_worker import run_once
from app.models import CloudAssessment, CloudAssessmentJob, Membership, Organization, now
from conftest import ANALYST, ORG_A, ORG_B, OWNER, headers, login
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from test_cloud_iam import IAM, EmptyInventory

IDENTITY = AWSAccountIdentity.from_role("arn:aws:iam::012345678901:role/security/mesh-reader")
P = Principal(ANALYST, ORG_A, "security_analyst")


def snapshot_data():
    normalizer = CloudNormalizer(ORG_A, IDENTITY, {"ec2": "us-east-1", "rds": "us-east-1"}, 200)
    normalizer.observe("s3", "s3.bucket", native="fixture-bucket", name="fixture-bucket")
    user = normalizer.observe(
        "iam",
        "iam.user",
        uid="AIDAFIXTURE123",
        arn="arn:aws:iam::012345678901:user/team/User",
        name="User",
    )
    normalizer.user_policy(
        user,
        {
            "PolicyArn": "arn:aws:iam::aws:policy/AdministratorAccess",
            "PolicyName": "AdministratorAccess",
        },
    )
    role = normalizer.observe(
        "iam",
        "iam.role",
        uid="AROAFIXTURE123",
        arn="arn:aws:iam::012345678901:role/team/Reader",
        name="Reader",
    )
    normalizer.role_statements(
        role,
        [
            {
                "Effect": "Allow",
                "Action": "sts:AssumeRole",
                "Principal": {"AWS": "*"},
                "Condition": {"StringEquals": {"external:secret": "DO_NOT_RETAIN"}},
            }
        ],
    )
    return normalizer.finish([], ["Fixture only; no live AWS calls"])


def persist(db, data=None):
    data = data or snapshot_data()
    report = Report(
        findings=[],
        errors=[],
        partial=False,
        coverage=["fixture"],
        limitations=["Fixture only"],
        normalized_context=data,
    )
    record = assessment_record(report, ORG_A)
    db.add(record)
    db.commit()
    return record


def test_normalized_snapshot_retains_evidence_and_never_claims_effective_access():
    data = snapshot_data()
    graph = Snapshot.model_validate(data)
    assert graph.envelope.partial
    assert len(graph.assets) == 2 and len(graph.principals) == 2
    assert graph.relationships[0].relationship_type == "policy_attached"
    assert graph.permissions[0].condition_state == "present"
    assert graph.permissions[0].effective_decision == "not_evaluated"
    assert "DO_NOT_RETAIN" not in str(data)
    assert all(item.reference.content_digest for item in graph.evidence)
    assert any(item.state == "unsupported" for item in graph.envelope.coverage)


@pytest.mark.parametrize(
    "mutation",
    ["tenant", "key", "evidence", "dangling_edge", "future", "partial", "synthetic", "fact"],
)
def test_snapshot_rejects_scope_integrity_and_uncertainty_violations(mutation):
    data = snapshot_data()
    if mutation == "tenant":
        data["assets"][0]["organization_id"] = ORG_B
    elif mutation == "key":
        data["principals"][0]["principal_key"] = "cp1_" + "0" * 64
    elif mutation == "evidence":
        data["evidence"] = []
    elif mutation == "dangling_edge":
        data["relationships"][0]["to"]["key"] = "ca1_" + "0" * 64
    elif mutation == "future":
        data["envelope"]["collection_started_at"] = (now() + timedelta(days=1)).isoformat()
    elif mutation == "partial":
        data["envelope"]["partial"] = False
    elif mutation == "synthetic":
        data["envelope"]["synthetic"] = True
    elif mutation == "fact":
        data["assets"][0]["facts"] = {
            "storage_encrypted": {"state": "unknown", "value": False, "evidence_refs": []}
        }
    with pytest.raises(ValidationError):
        Snapshot.model_validate(data)


def test_selection_pinned_pages_evidence_and_exact_resolution(db):
    record = persist(db)
    graph = Snapshot.model_validate(record.normalized_context)
    selection = context.get_context(db, P, scope=graph.envelope.scope, as_of=now())
    assert selection.state == "partial"
    assert str(selection.envelope.assessment_id) == record.id
    page = context.list_assets(db, P, assessment_id=record.id, limit=1)
    assert page.total == 2 and page.next_offset == 1
    assert context.list_assets(db, P, assessment_id=record.id, offset=99).total == 2
    assert context.list_principals(db, P, assessment_id=record.id).total == 2
    assert context.list_permissions(db, P, assessment_id=record.id).total == 1
    assert context.list_relationships(db, P, assessment_id=record.id).total == 1
    evidence = context.get_evidence(
        db, P, assessment_id=record.id, evidence_id=graph.evidence[0].reference.evidence_id
    )
    assert evidence.availability == "available"
    role = next(node for node in graph.principals if node.node_type == "iam.role")
    refs = [
        {
            "scope": role.scope,
            "node_type": role.node_type,
            "identity_kind": "arn",
            "provider_identity": role.arn,
        }
    ]
    result = context.resolve_references(db, P, assessment_id=record.id, references=refs)
    assert result[0].state == "matched" and result[0].candidate_keys == [role.principal_key]
    refs[0]["provider_identity"] = role.arn.lower()
    assert (
        context.resolve_references(db, P, assessment_id=record.id, references=refs)[0].state
        != "matched"
    )


@pytest.mark.parametrize("change", ["revoked", "role", "suspended", "tenant", "owner", "mfa"])
def test_reader_rechecks_authority_and_hides_foreign_snapshot(db, monkeypatch, change):
    record = persist(db)
    p = P
    if change == "revoked":
        db.get(Membership, (ORG_A, ANALYST)).active = False
    elif change == "role":
        db.get(Membership, (ORG_A, ANALYST)).role = "owner"
    elif change == "suspended":
        db.get(Organization, ORG_A).status = "suspended"
    elif change == "tenant":
        p = Principal(ANALYST, ORG_B, "security_analyst")
    elif change == "owner":
        p = Principal(OWNER, ORG_A, "owner")
    elif change == "mfa":
        monkeypatch.setattr(
            context,
            "settings",
            lambda: SimpleNamespace(require_privileged_mfa=True, test_mode=True),
        )
    db.flush()
    with pytest.raises(HTTPException) as error:
        context.list_assets(db, p, assessment_id=record.id)
    assert error.value.status_code == (404 if change == "tenant" else 403)


def test_newer_partial_is_selected_and_future_or_synthetic_is_not_used(db):
    older = persist(db)
    newer = persist(db)
    graph = Snapshot.model_validate(newer.normalized_context)
    selected = context.get_context(db, P, scope=graph.envelope.scope, as_of=now())
    assert str(selected.envelope.assessment_id) == newer.id
    before = Snapshot.model_validate(
        older.normalized_context
    ).envelope.collection_started_at - timedelta(seconds=1)
    assert (
        context.get_context(db, P, scope=graph.envelope.scope, as_of=before).state == "unavailable"
    )
    assert (
        context.get_context(db, P, scope=graph.envelope.scope, as_of=now(), synthetic=True).state
        == "unavailable"
    )
    assert (
        context.get_context(
            db, P, scope=graph.envelope.scope, as_of=now() + timedelta(hours=2)
        ).state
        == "stale"
    )
    wrong = graph.envelope.scope.model_copy(update={"provider_account_id": "999999999999"})
    assert context.get_context(db, P, scope=wrong, as_of=now()).state == "unavailable"


def test_legacy_snapshot_and_missing_evidence_are_explicit(db):
    record = CloudAssessment(
        organization_id=ORG_A,
        findings=[],
        errors=[],
        partial=False,
        coverage=[],
        limitations=["Legacy"],
    )
    db.add(record)
    db.commit()
    scope = Snapshot.model_validate(snapshot_data()).envelope.scope
    assert (
        context.get_context(db, P, scope=scope, as_of=now(), assessment_id=record.id).state
        == "unavailable"
    )
    with pytest.raises(HTTPException) as error:
        context.list_assets(db, P, assessment_id=record.id)
    assert error.value.status_code == 409
    with pytest.raises(HTTPException) as error:
        context.get_evidence(db, P, assessment_id=record.id, evidence_id=uuid4())
    assert error.value.status_code == 404


@pytest.mark.parametrize("limit,offset", [(0, 0), (101, 0), (True, 0), (1, -1), (1, 100001)])
def test_page_bounds_are_strict(db, limit, offset):
    record = persist(db)
    with pytest.raises(HTTPException) as error:
        context.list_assets(db, P, assessment_id=record.id, limit=limit, offset=offset)
    assert error.value.status_code == 422


def test_naive_cutoff_and_oversize_reference_batch_are_invalid(db):
    record = persist(db)
    scope = Snapshot.model_validate(record.normalized_context).envelope.scope
    with pytest.raises(HTTPException) as error:
        context.get_context(db, P, scope=scope, as_of=now().replace(tzinfo=None))
    assert error.value.status_code == 422
    node = record.normalized_context["principals"][0]
    reference = {
        "scope": node["scope"],
        "node_type": node["node_type"],
        "identity_kind": "arn",
        "provider_identity": node["arn"],
    }
    with pytest.raises(HTTPException) as error:
        context.resolve_references(db, P, assessment_id=record.id, references=[reference] * 101)
    assert error.value.status_code == 422


@pytest.mark.parametrize("cancel", [False, True])
def test_worker_publishes_one_immutable_snapshot_only_under_current_lease(db, monkeypatch, cancel):
    job = CloudAssessmentJob(organization_id=ORG_A, requested_by=ANALYST, request_key=str(uuid4()))
    db.add(job)
    db.commit()
    factory = sessionmaker(db.get_bind(), expire_on_commit=False)
    monkeypatch.setattr("app.cloud_worker.SessionFactory", factory)

    def runner(_):
        if cancel:
            with factory.begin() as other:
                other.get(CloudAssessmentJob, job.id).status = "cancelled"
        return {
            "findings": [],
            "errors": [],
            "partial": False,
            "coverage": [],
            "limitations": ["Fixture"],
            "normalized_context": snapshot_data(),
        }

    assert run_once(ORG_A, runner)
    db.expire_all()
    records = db.scalars(select(CloudAssessment)).all()
    assert len(records) == (0 if cancel else 1)
    if records:
        assert records[0].normalized_context["envelope"]["source_job_id"] == job.id
        assert db.get(CloudAssessmentJob, job.id).assessment_id == records[0].id


def test_synchronous_route_preserves_legacy_response_and_retains_graph(client, db, monkeypatch):
    result = {
        "findings": [],
        "errors": [],
        "partial": False,
        "coverage": [],
        "limitations": ["Fixture"],
        "normalized_context": snapshot_data(),
    }
    monkeypatch.setattr(
        "app.intelligence_api.configured_aws", lambda _: SimpleNamespace(assess=lambda: result)
    )
    login(ANALYST)
    response = client.post("/api/v1/vader/cloud/assess", headers=headers())
    assert response.status_code == 200, response.text
    assert "normalized_context" not in response.json()
    assert response.json()["partial"] is True
    assert db.get(CloudAssessment, response.json()["id"]).normalized_context


def test_actual_collector_normalizes_bounded_inventory_without_secret_fields():
    class Inventory(EmptyInventory):
        meta = SimpleNamespace(region_name="us-east-1")

        def list_buckets(self):
            return {"Buckets": [{"Name": "fixture-bucket", "SecretTag": "DO_NOT_RETAIN"}]}

    class IdentityInventory(IAM):
        def list_users(self):
            return {
                "Users": [
                    {
                        "UserName": "fixture-user",
                        "UserId": "AIDAFIXTURE123",
                        "Arn": "arn:aws:iam::012345678901:user/fixture-user",
                    }
                ]
            }

        def list_roles(self):
            return {
                "Roles": [
                    {
                        "RoleName": "Reader",
                        "RoleId": "AROAFIXTURE123",
                        "Arn": "arn:aws:iam::012345678901:role/Reader",
                        "AssumeRolePolicyDocument": {
                            "Statement": [
                                {
                                    "Effect": "Allow",
                                    "Action": "sts:AssumeRole",
                                    "Principal": {"AWS": "*"},
                                }
                            ]
                        },
                    }
                ]
            }

    clients = {name: Inventory() for name in ("s3", "ec2", "rds")}
    clients["iam"] = IdentityInventory()
    report = AWSAssessment(clients, account_identity=IDENTITY, organization_id=ORG_A).assess()
    graph = Snapshot.model_validate(report["normalized_context"])
    assert graph.principals and graph.assets and graph.permissions
    assert "DO_NOT_RETAIN" not in str(report)
    assert "DO_NOT_PERSIST" not in str(report)


def test_freshness_expiry_boundary_and_missing_observation():
    observed = now()
    timing = Times(
        observed_at=observed, collected_at=observed, fresh_until=observed + timedelta(hours=1)
    )
    assert freshness(timing, observed) == "fresh"
    assert freshness(timing, observed + timedelta(hours=1)) == "stale"
    assert freshness(timing, observed - timedelta(seconds=1)) == "unknown"


def test_complete_empty_scope_is_distinct_from_denied_empty_scope(db):
    for denied in (False, True):
        data = snapshot_data()
        data["assets"] = []
        data["principals"] = []
        data["permissions"] = []
        data["relationships"] = []
        data["evidence"] = []
        data["envelope"]["assessment_id"] = str(uuid4())
        s3 = next(item for item in data["envelope"]["requested_scopes"] if item["service"] == "s3")
        coverage = next(
            item for item in data["envelope"]["coverage"] if item["scope"]["service"] == "s3"
        )
        coverage.update(
            state="denied" if denied else "complete",
            observed_count=0,
            reason_code="access_denied" if denied else None,
        )
        data["envelope"].update(requested_scopes=[s3], coverage=[coverage], partial=denied)
        record = persist(db, data)
        selection = context.get_context(db, P, scope=s3, as_of=now(), assessment_id=record.id)
        assert selection.state == ("partial" if denied else "available")
        result = context.resolve_references(
            db,
            P,
            assessment_id=record.id,
            references=[
                {
                    "scope": s3,
                    "node_type": "s3.bucket",
                    "identity_kind": "scoped_native_id",
                    "provider_identity": "not-observed",
                }
            ],
        )
        assert result[0].state == ("unknown" if denied else "not_found")


def test_expired_evidence_cannot_establish_unique_identity(db):
    data = snapshot_data()
    for item in data["evidence"]:
        item.update(availability="expired", summary=None, reasons=["evidence_unavailable"])
    record = persist(db, data)
    node = record.normalized_context["principals"][0]
    result = context.resolve_references(
        db,
        P,
        assessment_id=record.id,
        references=[
            {
                "scope": node["scope"],
                "node_type": node["node_type"],
                "identity_kind": "arn",
                "provider_identity": node["arn"],
            }
        ],
    )
    assert result[0].state == "unknown" and result[0].candidate_keys == []
    evidence = context.get_evidence(
        db, P, assessment_id=record.id, evidence_id=data["evidence"][0]["reference"]["evidence_id"]
    )
    assert evidence.availability == "expired" and evidence.summary is None


def test_byte_limited_pages_advance_without_skipping_and_reject_oversize_records(db, monkeypatch):
    record = persist(db)
    first = context.list_assets(db, P, assessment_id=record.id, limit=1)
    from app.cloud_context_schema import wire_bytes

    monkeypatch.setattr(context, "MAX_PAGE_BYTES", wire_bytes(first) + 100)
    page = context.list_assets(db, P, assessment_id=record.id, limit=2)
    assert len(page.items) == 1 and page.next_offset == 1 and page.total == 2
    second = context.list_assets(db, P, assessment_id=record.id, offset=page.next_offset)
    assert second.items[0]["asset_key"] != page.items[0]["asset_key"]
    monkeypatch.setattr(context, "MAX_PAGE_BYTES", 10)
    with pytest.raises(HTTPException) as error:
        context.list_assets(db, P, assessment_id=record.id)
    assert error.value.status_code == 503


def test_snapshot_rejects_credential_fact_keys_and_misleading_arn_alias():
    data = snapshot_data()
    data["principals"][0]["arn"] = "arn:aws:iam::999999999999:user/Other"
    with pytest.raises(ValidationError):
        Snapshot.model_validate(data)
    data = snapshot_data()
    data["assets"][0]["facts"] = {
        "secret_access_key": {"state": "unknown", "value": None, "evidence_refs": []}
    }
    with pytest.raises(ValidationError):
        Snapshot.model_validate(data)


def test_unsupported_snapshot_version_and_unsealed_snapshot_are_conflicts(db):
    for changed in ({"schema_version": "2.0.0"}, {"publication_state": "running"}):
        data = snapshot_data()
        data["envelope"].update(changed)
        record = CloudAssessment(
            id=data["envelope"]["assessment_id"],
            organization_id=ORG_A,
            findings=[],
            partial=True,
            normalized_context=data,
        )
        db.add(record)
        db.commit()
        with pytest.raises(HTTPException) as error:
            context.list_assets(db, P, assessment_id=record.id)
        assert error.value.status_code == 409


def test_unknown_regional_identity_is_not_fabricated_as_global():
    normalizer = CloudNormalizer(ORG_A, IDENTITY, {}, 200)
    assert normalizer.observe("ec2", "ec2.security_group", native="sg-fixture") is None
    data = normalizer.finish([], ["Region unavailable"])
    assert not data["assets"]
    assert "identity_unresolved" in data["envelope"]["errors"]
    assert all(scope["service"] != "ec2" for scope in data["envelope"]["requested_scopes"])


def test_sts_reference_scope_does_not_hide_missing_regional_inventory():
    graph = CloudNormalizer(ORG_A, IDENTITY, {"ec2": "us-east-1"}, 200)
    role = graph.observe(
        "iam", "iam.role", arn="arn:aws:iam::012345678901:role/Role", uid="AROAFIXTURE123"
    )
    from app.cloud_iam_inventory import IAMInventory

    inventory = IAMInventory(None, graph, lambda: None)
    reference = role.evidence_refs[0]
    inventory.principal_reference(
        "arn:aws:sts::012345678901:assumed-role/Role/Session", "AWS", reference, graph.times()
    )
    snapshot = Snapshot.model_validate(graph.finish([], ["Fixture only"]))
    assert len(snapshot.envelope.requested_scopes) == 4
    assert "identity_unresolved" in snapshot.envelope.errors


def test_verified_collector_retains_root_summary_as_typed_facts_without_credentials():
    class RegionEmpty(EmptyInventory):
        meta = SimpleNamespace(region_name="us-east-1")

    clients = {name: RegionEmpty() for name in ("s3", "ec2", "rds")}
    clients["iam"] = IAM()
    result = AWSAssessment(clients, account_identity=IDENTITY, organization_id=ORG_A).assess()
    graph = Snapshot.model_validate(result["normalized_context"])
    root = next(node for node in graph.principals if node.node_type == "iam.account_root")
    assert root.facts["root_console_enabled"].value is True
    assert root.facts["root_mfa_enabled"].value is False
    assert root.facts["root_access_keys_present"].value is True
    assert root.evidence_refs[0].operation == "iam.account_summary"
    assert "DO_NOT_PERSIST" not in str(result)
