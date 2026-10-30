"""Exercise HR/investigation persistence on hosted PostgreSQL, then roll it all back.

Uses synthetic memberships (not Auth users) and a controlled salary effective-date
clock. No email, model endpoint, external account or Storage object is touched.
"""

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import HTTPException
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))

from app import workforce_api as workforce  # noqa: E402
from app.api import events as list_events  # noqa: E402
from app.api import project_create, project_decision  # noqa: E402
from app.auth import Principal  # noqa: E402
from app.core.config import SCIMBinding, settings  # noqa: E402
from app.core.db import assert_runtime_role, tenant_context  # noqa: E402
from app.enterprise_api import leave_decide, lifecycle_approve  # noqa: E402
from app.enterprise_schemas import Decision, FindingDecision, LeaveInput, LifecycleInput  # noqa: E402
from app.hr import execute_lifecycle, propose_lifecycle, request_leave  # noqa: E402
from app.intelligence_api import risk_evidence  # noqa: E402
from app.investigation_api import NoteInput, note_create  # noqa: E402
from app.models import (  # noqa: E402
    Anomaly,
    Employee,
    EmploymentChange,
    Finding,
    Incident,
    IncidentEvent,
    JobRole,
    Membership,
    Organization,
    Outbox,
    Repository,
    ScanJob,
    SecurityEvent,
    identifier,
)
from app.payroll import ComputeInput, RuleInput, compute, rule_create  # noqa: E402
from app.project_governance import review  # noqa: E402
from app.project_governance_api import PolicyInput as ApprovalPolicyInput  # noqa: E402
from app.project_governance_api import activity, policy_set  # noqa: E402
from app.risk_api import RiskAssessmentInput, RiskPolicyInput  # noqa: E402
from app.risk_api import assess as risk_assess  # noqa: E402
from app.risk_api import policy_create as risk_policy_create  # noqa: E402
from app.scan_api import finding_decide, finding_history, repository_remediation  # noqa: E402
from app.schemas import EventInput, ProjectDecision, ProjectInput  # noqa: E402
from app.services import verify_audit  # noqa: E402
from app.vader import ingest  # noqa: E402
from app.workflow_api import CancellationInput, lifecycle_compensation  # noqa: E402


def verify():
    engine = create_engine(os.environ["DATABASE_URL"])
    org_a, org_b, employee_user, hr, reviewer, analyst = [identifier() for _ in range(6)]
    employee = Employee(
        id=identifier(),
        organization_id=org_a,
        user_id=employee_user,
        name="Synthetic fixture",
        department="Verification",
        status="active",
    )
    original_bindings = settings().scim_bindings
    original_clock = workforce.now
    workforce.now = lambda: datetime(2030, 1, 1, tzinfo=UTC)
    checks = {}
    try:
        with Session(engine) as db:
            assert_runtime_role(db)
            for org in (org_a, org_b):
                tenant_context(db, org, hr)
                db.add(Organization(id=org, name="Rollback-only workflow verification"))
                db.flush()
                for user, role in (
                    (employee_user, "junior_developer"),
                    (hr, "hr"),
                    (reviewer, "hr"),
                    (analyst, "security_analyst"),
                ):
                    db.add(
                        Membership(
                            organization_id=org,
                            user_id=user,
                            email=user + "@example.invalid",
                            role=role,
                        )
                    )
                db.flush()
            tenant_context(db, org_a, hr)
            db.add(employee)
            db.flush()
            p, approval = Principal(hr, org_a, "hr"), Principal(reviewer, org_a, "hr")
            role = workforce.job_role_create(
                workforce.JobRoleInput(
                    title="Fixture engineer",
                    grade="T1",
                    version=1,
                    currency="INR",
                    minimum_base="1000.00",
                    maximum_base="2000.00",
                ),
                db,
                p,
            )
            change = workforce.employment_propose(
                workforce.EmploymentInput(
                    employee_id=employee.id,
                    job_role_id=role.id,
                    base="1500.00",
                    effective_on="2030-01-01",
                    reason="Synthetic approved salary fixture",
                ),
                db,
                p,
            )
            try:
                workforce.employment_decide(change.id, Decision(decision="approved"), db, p)
            except HTTPException as exc:
                assert exc.status_code == 403
            else:
                raise AssertionError("Self approval was accepted")
            workforce.employment_decide(change.id, Decision(decision="approved"), db, approval)
            terms = workforce.employment_apply(change.id, db, p)
            assert terms.base == 1500 and terms.currency == "INR"
            assert workforce.employment_apply(change.id, db, p).id == terms.id
            checks["independent_salary_approval_and_idempotent_snapshot"] = "passed"
            rule = rule_create(
                RuleInput(name="Fixture base", version=1, currency="INR", components=[]), db, p
            )
            try:
                compute(
                    ComputeInput(
                        employee_id=employee.id, rule_id=rule.id, base="1600.00", period="2030-01"
                    ),
                    db,
                    p,
                )
            except HTTPException as exc:
                assert exc.status_code == 409
            else:
                raise AssertionError("Unapproved payroll base was accepted")
            payroll = compute(
                ComputeInput(
                    employee_id=employee.id, rule_id=rule.id, base="1500.00", period="2030-01"
                ),
                db,
                p,
            )
            assert payroll.payroll.net == 1500
            checks["payroll_matches_approved_salary"] = "passed"
            workforce.allowance_set(
                employee.id,
                2030,
                workforce.AllowanceInput(allowance_days=1, counting="calendar"),
                db,
                p,
            )
            leave = request_leave(
                db,
                Principal(employee_user, org_a, "junior_developer"),
                LeaveInput(
                    employee_id=employee.id,
                    starts_on="2030-01-02",
                    ends_on="2030-01-02",
                    reason="Synthetic fixture",
                ),
            )
            try:
                request_leave(
                    db,
                    p,
                    LeaveInput(
                        employee_id=employee.id,
                        starts_on="2030-01-03",
                        ends_on="2030-01-03",
                        reason="Must exceed reservation",
                    ),
                )
            except HTTPException as exc:
                assert exc.status_code == 409
            else:
                raise AssertionError("Over-reserved leave was accepted")
            leave_decide(leave.id, Decision(decision="approved"), db, p)
            checks["leave_reservation_and_review_enforcement"] = "passed"
            workforce.allowance_set(
                employee.id,
                2031,
                workforce.AllowanceInput(
                    allowance_days=0, counting="calendar", holidays=["2031-01-01"]
                ),
                db,
                p,
            )
            request_leave(
                db,
                Principal(employee_user, org_a, "junior_developer"),
                LeaveInput(
                    employee_id=employee.id,
                    starts_on="2031-01-01",
                    ends_on="2031-01-01",
                    reason="Holiday fixture",
                ),
            )
            assert workforce.allowance_get(employee.id, 2031, db, p).reserved_days == 0
            try:
                workforce.allowance_set(
                    employee.id,
                    2031,
                    workforce.AllowanceInput(allowance_days=1, counting="calendar"),
                    db,
                    p,
                )
            except HTTPException as exc:
                assert exc.status_code == 409
            else:
                raise AssertionError("Reserved holiday calendar was modified")
            checks["holiday_persistence_exclusion_and_reserved_calendar_guard"] = "passed"
            repository = Repository(
                id=identifier(),
                organization_id=org_a,
                full_name="fixture/rollback-only",
                installation_id=1,
            )
            db.add(repository)
            db.flush()
            for scanner, state in [("bandit", "open"), ("bandit", "resolved"), ("osv", "open")]:
                db.add(
                    Finding(
                        organization_id=org_a,
                        repository_id=repository.id,
                        scanner=scanner,
                        rule_id="fixture",
                        severity="high",
                        status=state,
                        file_path="fixture.py",
                        line=1,
                    )
                )
            db.flush()
            reporting_actor = Principal(analyst, org_a, "security_analyst")
            page = repository_remediation(
                repository.id,
                db,
                reporting_actor,
                limit=1,
                offset=0,
                scanner=None,
                severity=None,
                observed_since=None,
            )
            assert page["total_groups"] == 2 and page["groups"][0]["total"] == 2
            assert page["groups"][0]["open"] == page["groups"][0]["resolved"] == 1
            empty = repository_remediation(
                repository.id,
                db,
                reporting_actor,
                limit=1,
                offset=10,
                scanner=None,
                severity=None,
                observed_since=None,
            )
            assert empty["groups"] == [] and empty["total_groups"] == 2
            checks["postgresql_remediation_window_counts_and_empty_offset"] = "passed"
            incident = Incident(
                id=identifier(),
                organization_id=org_a,
                actor_id=employee_user,
                fingerprint=identifier().replace("-", ""),
                event_ids=[],
                risk=0,
                explanation="Synthetic verification",
                synthetic=True,
            )
            db.add(incident)
            db.flush()
            signal = SecurityEvent(
                id=identifier(),
                organization_id=org_a,
                source_id=identifier(),
                occurred_at=datetime.now(UTC),
                actor_id=employee_user,
                category="api",
                action="fixture",
                result="success",
                count=1,
                synthetic=True,
            )
            db.add(signal)
            db.flush()
            db.add(
                IncidentEvent(organization_id=org_a, incident_id=incident.id, event_id=signal.id)
            )
            db.add(
                Anomaly(
                    organization_id=org_a,
                    event_id=signal.id,
                    rule="fixture",
                    weight=20,
                    explanation="Fixture",
                )
            )
            db.flush()
            projection = risk_evidence(
                incident.id, db, Principal(analyst, org_a, "security_analyst")
            )
            assert projection.retained_evidence_score == 20 and projection.stored_score == 0
            assert projection.evidence_complete and projection.original_model_version is None
            assert incident.risk == 0
            checks["retained_risk_projection_sql_without_historical_score_mutation"] = "passed"
            note = note_create(
                incident.id,
                NoteInput(body="Synthetic investigation note"),
                db,
                Principal(analyst, org_a, "security_analyst"),
            )
            assert note.author_id == analyst
            checks["analyst_investigation_note_persistence"] = "passed"
            owner, senior_a, senior_b = identifier(), identifier(), identifier()
            for uid, role_name in (
                (owner, "owner"),
                (senior_a, "senior_developer"),
                (senior_b, "senior_developer"),
            ):
                db.add(
                    Membership(
                        organization_id=org_a,
                        user_id=uid,
                        email=uid + "@example.invalid",
                        role=role_name,
                    )
                )
            db.flush()
            owner_principal = Principal(owner, org_a, "owner")
            risk_policy = risk_policy_create(RiskPolicyInput(), db, owner_principal)
            request = RiskAssessmentInput(request_key=identifier(), synthetic=True)
            risk_record = risk_assess(request, db, Principal(analyst, org_a, "security_analyst"))
            assert risk_record.policy_id == risk_policy.id
            assert (
                risk_record.result["overall_score"] == 40 and risk_record.result["partial"] is True
            )
            assert risk_record.result["components"]["api"]["score"] == 40
            assert (
                risk_assess(request, db, Principal(analyst, org_a, "security_analyst")).id
                == risk_record.id
            )
            checks["versioned_unified_risk_snapshot_sql_and_idempotency"] = "passed"
            policy_set(
                ApprovalPolicyInput(version=1, required_senior_reviews=2), db, owner_principal
            )
            developer = Principal(employee_user, org_a, "junior_developer")
            project = project_create(
                ProjectInput(name="Synthetic project", description="Rollback-only fixture"),
                db,
                developer,
            )
            review(db, Principal(senior_a, org_a, "senior_developer"), project.id)
            try:
                project_decision(
                    project.id, ProjectDecision(decision="approved"), owner_principal, db
                )
            except HTTPException as exc:
                assert exc.status_code == 409
            else:
                raise AssertionError("Owner approval bypassed configured senior review count")
            review(db, Principal(senior_b, org_a, "senior_developer"), project.id)
            project_decision(project.id, ProjectDecision(decision="approved"), owner_principal, db)
            assert (
                project.status == "approved"
                and project.approval_policy["required_senior_reviews"] == 2
            )
            assert activity(project.id, db, developer)
            checks["versioned_project_review_policy_and_resource_scoped_activity"] = "passed"
            source_finding = db.scalar(
                select(Finding).where(
                    Finding.organization_id == org_a,
                    Finding.repository_id == repository.id,
                    Finding.status == "open",
                )
            )
            finding_decide(
                source_finding.id, FindingDecision(status="accepted_risk"), db, reporting_actor
            )
            transitions = finding_history(source_finding.id, db, reporting_actor)
            assert transitions["changes"][-1]["to_status"] == "accepted_risk"
            assert transitions["changes"][-1]["actor_id"] == analyst
            checks["finding_accepted_risk_and_explicit_audited_transition_sql"] = "passed"
            metadata = EventInput(
                source_id=identifier(),
                occurred_at=datetime.now(UTC),
                actor_id=identifier(),
                category="device",
                action="observed",
                result="success",
                context={
                    "source": {"kind": "device", "name": "fixture"},
                    "device": {"new_device": True},
                    "reported_severity": "low",
                },
            )
            normalized = ingest(db, reporting_actor, metadata)
            assert ingest(db, reporting_actor, metadata).duplicate
            selected = list_events(
                db,
                reporting_actor,
                limit=50,
                offset=0,
                category="device",
                actor_id=metadata.actor_id,
                synthetic=False,
                source_kind="device",
                reported_severity="low",
            )
            assert [item.id for item in selected] == [normalized.event_id]
            for table in ("security_events", "anomalies"):
                try:
                    with db.begin_nested():
                        db.execute(text(f'UPDATE "{table}" SET id=id'))
                except DBAPIError as error:
                    assert error.orig.sqlstate == "42501"
                else:
                    raise AssertionError("Observation mutation was accepted")
            checks["normalized_context_json_filters_receipts_and_immutable_runtime_evidence"] = (
                "passed"
            )
            original_department = employee.department
            lifecycle = propose_lifecycle(
                db,
                p,
                LifecycleInput(
                    employee_id=employee.id, kind="transfer", department="Fixture transfer"
                ),
            )
            lifecycle_approve(lifecycle.id, Decision(decision="approved"), db, owner_principal)
            execute_lifecycle(db, p, lifecycle.id)
            inverse = lifecycle_compensation(
                lifecycle.id,
                CancellationInput(reason="Reverse the fictional transfer after independent review"),
                db,
                p,
            )
            assert inverse.status == "proposed" and employee.department == "Fixture transfer"
            lifecycle_approve(inverse.id, Decision(decision="approved"), db, owner_principal)
            execute_lifecycle(db, p, inverse.id)
            assert employee.department == original_department and lifecycle.status == "completed"
            checks["reviewed_lifecycle_inverse_plan_and_fresh_approval_sql"] = "passed"
            for table in (
                "job_roles",
                "employment_terms",
                "incident_notes",
                "payroll_calculations",
                "project_approval_policies",
                "project_reviews",
                "risk_policies",
                "risk_assessments",
            ):
                try:
                    with db.begin_nested():
                        db.execute(text(f'UPDATE "{table}" SET id=id'))
                except DBAPIError as exc:
                    assert exc.orig.sqlstate == "42501"
                else:
                    raise AssertionError("Runtime immutable-record update was accepted")
            checks["runtime_cannot_update_immutable_workforce_or_investigation_records"] = "passed"
            tenant_context(db, org_b, hr)
            foreign = JobRole(
                id=identifier(),
                organization_id=org_b,
                title="Foreign fixture",
                grade="T1",
                version=1,
                currency="INR",
                minimum_base=0,
                maximum_base=2000,
            )
            db.add(foreign)
            db.flush()
            tenant_context(db, org_a, hr)
            try:
                with db.begin_nested():
                    db.add(
                        EmploymentChange(
                            organization_id=org_a,
                            employee_id=employee.id,
                            job_role_id=foreign.id,
                            base=1000,
                            effective_on=datetime(2031, 1, 1).date(),
                            reason="Forbidden fixture",
                            proposed_by=hr,
                        )
                    )
                    db.flush()
            except DBAPIError as exc:
                assert exc.orig.sqlstate == "23503"
            else:
                raise AssertionError("Composite foreign key allowed a foreign tenant job role")
            checks["composite_tenant_fk_rejects_foreign_job_role"] = "passed"
            from app.enterprise_schemas import BudgetInput, CostInput
            from app.finance import budget_variances, record_budget, record_cost, summarize

            tenant_context(db, org_a, owner)
            cost_body = CostInput(
                request_key=identifier(),
                period="2026-10",
                department="Synthetic",
                category="cloud",
                currency="INR",
                amount="10",
                billing_provider="aws",
                usage_quantity="2",
                usage_unit="hours",
            )
            cost = record_cost(db, owner_principal, cost_body)
            assert record_cost(db, owner_principal, cost_body).id == cost.id
            assert summarize(db, owner_principal, "INR").total == 10
            budget_body = BudgetInput(period="2026-10", currency="INR", amount="20")
            budget = record_budget(db, owner_principal, budget_body)
            assert record_budget(db, owner_principal, budget_body).id == budget.id
            variance = budget_variances(db, owner_principal, "INR", 50, 0)[0]
            assert variance["variance"] == -10 and variance["variance_percent"] == -50
            checks["finance_actor_bound_replay_usage_and_budget_variance_sql"] = "passed"
            from app.rehire import RehireActivation, activate_rehire

            tenant_context(db, org_a, hr)
            employee.verification_status = "approved"
            offboard = propose_lifecycle(
                db, p, LifecycleInput(employee_id=employee.id, kind="offboarding")
            )
            lifecycle_approve(offboard.id, Decision(decision="approved"), db, owner_principal)
            execute_lifecycle(db, p, offboard.id)
            rehiring = propose_lifecycle(
                db,
                p,
                LifecycleInput(
                    employee_id=employee.id,
                    kind="rehire",
                    role="junior_developer",
                    department="Synthetic rehire",
                ),
            )
            lifecycle_approve(rehiring.id, Decision(decision="approved"), db, owner_principal)
            execute_lifecycle(db, p, rehiring.id)
            assert not db.get(Membership, (org_a, employee_user)).active
            activate_rehire(
                db,
                owner_principal,
                rehiring.id,
                RehireActivation(
                    reference="synthetic-provider-session-and-external-access-attestation",
                    provider_sessions_revoked=True,
                    external_access_reviewed=True,
                ),
            )
            assert db.get(Membership, (org_a, employee_user)).active
            assert db.get(Membership, (org_a, employee_user)).access_not_before is not None
            checks[
                "reviewed_rehire_sql_inactive_until_owner_attestation_and_fresh_token_boundary"
            ] = "passed"
            from app.provisioning import cancel_provisioning, provisioning_context

            settings().scim_bindings = {
                **original_bindings,
                org_a: SCIMBinding(
                    base_url="https://synthetic-provider.example.invalid/v2",
                    token="fixture-no-live-provider-key",
                    allow_provisioning=True,
                ),
            }
            provisioning = propose_lifecycle(
                db,
                p,
                LifecycleInput(employee_id=employee.id, kind="onboarding", provision_scim=True),
            )
            lifecycle_approve(provisioning.id, Decision(decision="approved"), db, owner_principal)
            execute_lifecycle(db, p, provisioning.id)
            _, _, _, intent = provisioning_context(db, org_a, provisioning.id)
            message = db.scalar(
                select(Outbox).where(
                    Outbox.organization_id == org_a,
                    Outbox.topic == "lifecycle.scim.provision",
                    Outbox.payload["subject"].as_string() == intent["subject"],
                )
            )
            assert message.status == "pending" and message.payload["creation_sent"] is False
            cancel_provisioning(
                db, owner_principal, provisioning.id, "synthetic-external-revocation-attestation"
            )
            assert (
                message.status == "cancelled" and db.get(Membership, (org_a, employee_user)).active
            )
            checks["reviewed_provisioning_intent_queue_and_cancel_sql_without_provider_calls"] = (
                "passed"
            )
            from app.scan_api import findings as scoped_findings

            scan = ScanJob(
                organization_id=org_a,
                repository_id=repository.id,
                requested_by=analyst,
                request_key=identifier(),
                commit_sha="a" * 40,
                status="completed",
            )
            db.add(scan)
            db.flush()
            observed = Finding(
                organization_id=org_a,
                repository_id=repository.id,
                scanner="osv",
                rule_id="OSV-SYNTHETIC",
                severity="info",
                file_path="dependency-manifest",
                line=1,
                scan_job_id=scan.id,
                commit_sha=scan.commit_sha,
                dependency={"name": "synthetic", "ecosystem": "PyPI", "version": "1"},
            )
            db.add(observed)
            db.flush()
            rows = scoped_findings(
                repository.id,
                db,
                reporting_actor,
                scan_job_id=scan.id,
                commit_sha="a" * 40,
                dependency_name="synthetic",
            )
            assert len(rows) == 1 and rows[0].id == observed.id
            assert source_finding.scan_job_id is None
            try:
                with db.begin_nested():
                    db.add(
                        Finding(
                            organization_id=org_a,
                            repository_id=repository.id,
                            scanner="bandit",
                            rule_id="B307",
                            severity="high",
                            file_path="a.py",
                            line=1,
                            scan_job_id=scan.id,
                            commit_sha="b" * 40,
                        )
                    )
                    db.flush()
            except DBAPIError as error:
                assert error.orig.sqlstate == "23503"
            else:
                raise AssertionError("Finding could be bound to the wrong scan commit")
            checks["finding_commit_dependency_filters_and_provenance_fk_sql"] = "passed"
            from app.finding_identity import identities, index_observations

            indexed = index_observations(db, reporting_actor, repository.id, 500)
            assert indexed["linked_observations"] >= 2 and indexed["remaining_unindexed"] == 0
            assert source_finding.scan_job_id is None and source_finding.commit_sha is None
            groups = identities(db, reporting_actor, repository.id, 100, 0)
            assert groups["total_groups"] >= 2 and groups["unindexed_observations"] == 0
            assert any(group["distinct_scans"] == 1 for group in groups["groups"])
            assert (
                index_observations(db, reporting_actor, repository.id, 500)["linked_observations"]
                == 0
            )
            checks["exact_finding_identity_index_history_and_legacy_provenance"] = "passed"
            from decimal import Decimal

            from app.ai_usage import usage_summary
            from app.models import AIUsage, now

            for currency, cost in (("USD", Decimal("1.5")), ("EUR", Decimal("2")), (None, None)):
                db.add(
                    AIUsage(
                        organization_id=org_a,
                        provider="gateway",
                        purpose="owner",
                        model="synthetic-only",
                        input_units=10,
                        output_units=5,
                        billing_currency=currency,
                        estimated_cost=cost,
                    )
                )
            db.flush()
            usage = usage_summary(db, owner_principal, now().strftime("%Y-%m"), 50, 0)
            assert (
                usage.total_groups == 3
                and sum(group.recorded_requests for group in usage.groups) == 3
            )
            assert any(
                group.currency is None
                and group.known_estimated_cost is None
                and group.unpriced_requests == 1
                for group in usage.groups
            )
            assert usage_summary(db, owner_principal, usage.month, 50, 99).total_groups == 3
            checks["currency_separated_recorded_ai_usage_summary_sql"] = "passed"
            from app.correlation import CorrelationConfig, PolicyChange, create_policy
            from app.correlation_api import policy_get, policy_history

            correlation = create_policy(
                db,
                reporting_actor,
                PolicyChange(
                    expected_version=0,
                    configuration=CorrelationConfig(
                        minimum_categories=2, minimum_events=2, link_mode="session"
                    ),
                ),
            )
            correlation_actor = "synthetic-correlation-" + identifier()
            for category, result, count in (
                ("authentication", "failure", 8),
                ("download", "success", 200),
            ):
                outcome = ingest(
                    db,
                    reporting_actor,
                    EventInput(
                        source_id=identifier(),
                        actor_id=correlation_actor,
                        category=category,
                        action="synthetic",
                        result=result,
                        count=count,
                        occurred_at=now(),
                        session_id="synthetic-session",
                    ),
                )
            correlated = db.get(Incident, outcome.incident_id)
            assert (
                outcome.correlation_status == "matched"
                and correlated.correlation_policy_id == correlation.id
            )
            assert correlated.correlation_snapshot["policy_version"] == 1
            assert policy_get(db, reporting_actor).version == 1
            assert policy_history(db, reporting_actor, 50, 99).total_policies == 1
            try:
                with db.begin_nested():
                    db.execute(
                        text("UPDATE incidents SET correlation_snapshot='{}'::json WHERE id=:id"),
                        {"id": correlated.id},
                    )
            except DBAPIError as error:
                assert error.orig.sqlstate == "P0001"
            else:
                raise AssertionError("Stored correlation provenance could be rewritten")
            checks["versioned_correlation_policy_matching_and_immutable_incident_snapshot_sql"] = (
                "passed"
            )
            assert verify_audit(db, p)["valid"]
            checks["workflow_audit_hash_integrity"] = "passed"
            db.rollback()
            tenant_context(db, org_a, hr)
            assert db.scalar(select(Organization).where(Organization.id == org_a)) is None
            checks["all_synthetic_workflow_records_rolled_back"] = "passed"
    finally:
        settings().scim_bindings = original_bindings
        workforce.now = original_clock
        engine.dispose()
    return {
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "checks": checks,
        "limitations": [
            "Synthetic memberships bypass provider authentication intentionally.",
            "Salary effective-date clock is controlled for rollback-only validation.",
            "No external integration was called.",
        ],
    }


if __name__ == "__main__":
    try:
        report = verify()
    except Exception as exc:
        print(json.dumps({"failed": type(exc).__name__}))
        raise SystemExit(1) from None
    (ROOT / "docs/supabase-workflow-results.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
