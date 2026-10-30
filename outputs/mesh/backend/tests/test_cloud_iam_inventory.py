import json
from copy import deepcopy
from urllib.parse import quote

import pytest
from app.cloud_context_schema import Snapshot
from app.cloud_iam_inventory import IAMInventory, policy_document
from app.cloud_identity import AWSAccountIdentity
from app.cloud_normalizer import CloudNormalizer
from botocore.exceptions import ClientError
from conftest import ORG_A

ACCOUNT = "012345678901"
POLICY = "arn:aws:iam::aws:policy/ReadOnlyAccess"
DOCUMENT = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": ["s3:GetObject"],
            "Resource": ["arn:aws:s3:::fixture/*"],
            "Condition": {"StringEquals": {"secret:label": "MUST_NOT_PERSIST"}},
        },
        {
            "Effect": "Deny",
            "NotAction": "iam:GetRole",
            "NotResource": "arn:aws:iam::012345678901:role/Excepted",
        },
    ],
}


class IAM:
    def __init__(self):
        self.calls = []
        self.page = {
            "IsTruncated": False,
            "GroupDetailList": [
                {
                    "GroupName": "Readers",
                    "GroupId": "AGPAFIXTURE123",
                    "Arn": f"arn:aws:iam::{ACCOUNT}:group/team/Readers",
                    "GroupPolicyList": [
                        {"PolicyName": "Inline", "PolicyDocument": quote(json.dumps(DOCUMENT))}
                    ],
                    "AttachedManagedPolicies": [{"PolicyArn": POLICY}],
                }
            ],
            "UserDetailList": [
                {
                    "UserName": "User",
                    "UserId": "AIDAFIXTURE123",
                    "Arn": f"arn:aws:iam::{ACCOUNT}:user/User",
                    "GroupList": ["Readers"],
                    "PermissionsBoundary": {"PermissionsBoundaryArn": POLICY},
                    "Tags": [{"Key": "private", "Value": "MUST_NOT_PERSIST"}],
                }
            ],
            "RoleDetailList": [
                {
                    "RoleName": "Role",
                    "RoleId": "AROAFIXTURE123",
                    "Arn": f"arn:aws:iam::{ACCOUNT}:role/Role",
                    "AttachedManagedPolicies": [{"PolicyArn": POLICY}],
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
            ],
        }

    def get_account_authorization_details(self, **kwargs):
        self.calls.append(("details", kwargs))
        return deepcopy(self.page)

    def get_policy(self, **kwargs):
        self.calls.append(("profile", kwargs))
        return {
            "Policy": {
                "Arn": kwargs["PolicyArn"],
                "PolicyName": "ReadOnlyAccess",
                "PolicyId": "ANPAFIXTURE123",
                "DefaultVersionId": "v3",
            }
        }

    def get_policy_version(self, **kwargs):
        self.calls.append(("version", kwargs))
        return {
            "PolicyVersion": {
                "VersionId": "v3",
                "IsDefaultVersion": True,
                "Document": deepcopy(DOCUMENT),
            }
        }


def collect(client=None, budget=200):
    graph = CloudNormalizer(
        ORG_A, AWSAccountIdentity.from_role(f"arn:aws:iam::{ACCOUNT}:role/mesh-reader"), {}, 200
    )
    count = 0

    def guard():
        nonlocal count
        count += 1
        if count > budget:
            raise RuntimeError("Budget exceeded")

    inventory = IAMInventory(client or IAM(), graph, guard)
    inventory.collect()
    return Snapshot.model_validate(graph.finish([], ["Synthetic SDK fixture only"])), inventory


def test_authorization_inventory_collects_groups_membership_policies_and_boundaries():
    client = IAM()
    graph, inventory = collect(client)
    assert {node.node_type for node in graph.assets} == {"iam.group", "iam.policy"}
    assert {node.node_type for node in graph.principals} == {"iam.user", "iam.role"}
    assert {edge.relationship_type for edge in graph.relationships} == {
        "member_of",
        "policy_attached",
        "boundary_attached",
    }
    assert {item.policy_kind for item in graph.permissions} == {
        "identity_inline",
        "identity_managed",
        "permissions_boundary",
        "trust",
    }
    assert all(item.effective_decision == "not_evaluated" for item in graph.permissions)
    assert any(
        item.not_actions == ["iam:GetRole"] and item.not_resources for item in graph.permissions
    )
    assert "MUST_NOT_PERSIST" not in graph.model_dump_json()
    assert len([call for call in client.calls if call[0] == "version"]) == 1
    assert all(entry.state == "complete" for name, entry in inventory.graph.layer_coverage.items())
    assert graph.envelope.partial
    assert any(
        entry.check == "iam.scp" and entry.state == "unsupported"
        for entry in graph.envelope.coverage
    )


def test_group_membership_resolves_across_pages_without_name_only_nodes():
    client = IAM()
    original = deepcopy(client.page)

    def details(**kwargs):
        if "Marker" not in kwargs:
            return {
                "UserDetailList": original["UserDetailList"],
                "IsTruncated": True,
                "Marker": "next",
            }
        assert kwargs["Marker"] == "next"
        return {"GroupDetailList": original["GroupDetailList"], "IsTruncated": False}

    client.get_account_authorization_details = details
    graph, _ = collect(client)
    assert any(edge.relationship_type == "member_of" for edge in graph.relationships)
    group = next(node for node in graph.assets if node.node_type == "iam.group")
    assert group.identity_kind == "provider_uid"


def test_denied_inventory_is_explicit_and_retains_no_empty_complete_graph():
    client = IAM()

    def denied(**kwargs):
        raise ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "MUST_NOT_PERSIST"}},
            "GetAccountAuthorizationDetails",
        )

    client.get_account_authorization_details = denied
    graph, inventory = collect(client)
    assert not graph.assets and not graph.principals
    assert all(entry.state == "denied" for entry in inventory.graph.layer_coverage.values())
    assert "access_denied" in graph.envelope.errors
    assert "MUST_NOT_PERSIST" not in graph.model_dump_json()


def test_policy_denial_preserves_membership_and_marks_documents_incomplete():
    client = IAM()

    def denied(**kwargs):
        raise ClientError({"Error": {"Code": "AccessDenied"}}, "GetPolicy")

    client.get_policy = denied
    graph, inventory = collect(client)
    assert any(edge.relationship_type == "member_of" for edge in graph.relationships)
    assert inventory.graph.layer_coverage["managed_policy_documents"].state == "denied"
    assert inventory.graph.layer_coverage["boundaries"].state == "denied"
    assert any(item.policy_kind == "identity_inline" for item in graph.permissions)


def test_budget_exhaustion_cannot_claim_completed_layers():
    graph, inventory = collect(budget=2)
    assert graph.envelope.partial
    assert any(entry.state != "complete" for entry in inventory.graph.layer_coverage.values())


@pytest.mark.parametrize("marker", [None, "", 42, "repeated"])
def test_missing_or_repeated_continuation_is_partial(marker):
    client = IAM()
    client.page = {"IsTruncated": True, "Marker": marker}
    graph, inventory = collect(client)
    assert graph.envelope.partial
    assert all(entry.state == "partial" for entry in inventory.graph.layer_coverage.values())


def test_unknown_group_is_not_invented_from_name():
    client = IAM()
    client.page["GroupDetailList"] = []
    graph, inventory = collect(client)
    assert not any(edge.relationship_type == "member_of" for edge in graph.relationships)
    assert inventory.graph.layer_coverage["groups_membership"].state == "partial"


@pytest.mark.parametrize(
    "document",
    [
        None,
        [],
        {"Statement": []},
        {"Statement": [{"Effect": "Allow", "Action": "*", "NotAction": "iam:*", "Resource": "*"}]},
        {
            "Statement": [
                {"Effect": "Allow", "Action": "*", "Resource": "*", "Condition": "unknown"}
            ]
        },
    ],
)
def test_malformed_policy_does_not_create_approximate_permissions(document):
    client = IAM()
    client.page["GroupDetailList"][0]["GroupPolicyList"][0]["PolicyDocument"] = document
    graph, inventory = collect(client)
    assert inventory.graph.layer_coverage["inline_policies"].state == "partial"
    assert not any(item.policy_kind == "identity_inline" for item in graph.permissions)


def test_policy_version_drift_fails_closed():
    client = IAM()
    client.get_policy_version = lambda **kwargs: {
        "PolicyVersion": {"VersionId": "v4", "IsDefaultVersion": True, "Document": DOCUMENT}
    }
    graph, inventory = collect(client)
    assert inventory.graph.layer_coverage["managed_policy_documents"].state == "partial"
    assert not any(item.policy_kind == "identity_managed" for item in graph.permissions)


def test_policy_parser_bounds_structure_before_retention():
    nested = {}
    for _ in range(40):
        nested = {"condition": nested}
    with pytest.raises(ValueError):
        policy_document(nested)
    with pytest.raises(ValueError):
        policy_document("x" * (512 * 1024 + 1))


def test_trust_references_preserve_external_ownership_and_service_uncertainty():
    client = IAM()
    client.page["RoleDetailList"][0]["AssumeRolePolicyDocument"] = {
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "sts:AssumeRole",
                "Principal": {
                    "AWS": "arn:aws:iam::999999999999:role/External",
                    "Service": "ec2.amazonaws.com",
                },
                "Condition": {"StringEquals": {"private": "MUST_NOT_PERSIST"}},
            }
        ]
    }
    graph, inventory = collect(client)
    edges = [edge for edge in graph.relationships if edge.relationship_type == "trusts_principal"]
    assert len(edges) == 2
    assert all(
        edge.condition_state == "present"
        and edge.effective_decision == "not_evaluated"
        and edge.resolution == "external_reference"
        for edge in edges
    )
    targets = [node for node in graph.principals if node.lifecycle_state == "unknown"]
    assert {node.ownership for node in targets} == {"external_account", "aws_service"}
    assert all(node.identity_strength == "scoped_reference" for node in targets)
    assert "MUST_NOT_PERSIST" not in graph.model_dump_json()


def test_trust_to_collected_principal_uses_its_provider_uid():
    client = IAM()
    user = client.page["UserDetailList"][0]
    client.page["RoleDetailList"][0]["AssumeRolePolicyDocument"] = {
        "Statement": [
            {"Effect": "Allow", "Action": "sts:AssumeRole", "Principal": {"AWS": user["Arn"]}}
        ]
    }
    graph, _ = collect(client)
    edges = [edge for edge in graph.relationships if edge.relationship_type == "trusts_principal"]
    assert len(edges) == 1
    node = next(node for node in graph.principals if node.principal_key == edges[0].to.key)
    assert node.provider_uid == user["UserId"] and node.lifecycle_state == "observed_present"


def test_wildcard_and_deny_trust_never_create_verified_access_edges():
    client = IAM()
    client.page["RoleDetailList"][0]["AssumeRolePolicyDocument"] = {
        "Statement": [
            {"Effect": "Allow", "Action": "sts:AssumeRole", "Principal": "*"},
            {
                "Effect": "Deny",
                "Action": "sts:AssumeRole",
                "Principal": {"AWS": "arn:aws:iam::999999999999:root"},
            },
        ]
    }
    graph, _ = collect(client)
    assert not any(edge.relationship_type == "trusts_principal" for edge in graph.relationships)
    assert len([item for item in graph.permissions if item.policy_kind == "trust"]) == 2
    assert not any(node.arn and "999999999999" in node.arn for node in graph.principals)


def test_policy_parser_preserves_percent_literals_in_already_decoded_json():
    document = {
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "s3:GetObject",
                "Resource": "arn:aws:s3:::bucket/key%2Fpart",
            }
        ]
    }
    assert policy_document(json.dumps(document)) == document
    assert policy_document(quote(json.dumps(document))) == document


def test_account_shorthand_and_root_arn_resolve_one_delegation_reference():
    client = IAM()
    client.page["RoleDetailList"][0]["AssumeRolePolicyDocument"] = {
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "sts:AssumeRole",
                "Principal": {"AWS": ["999999999999", "arn:aws:iam::999999999999:root"]},
            }
        ]
    }
    graph, _ = collect(client)
    roots = [node for node in graph.principals if node.node_type == "iam.account_root"]
    assert len(roots) == 1 and roots[0].native_id == "999999999999"
    assert roots[0].lifecycle_state == "unknown" and roots[0].principal_type == "external_reference"
    assert roots[0].arn == "arn:aws:iam::999999999999:root"


def test_session_reference_is_distinct_from_role_and_does_not_invent_session_activity():
    client = IAM()
    client.page["RoleDetailList"][0]["AssumeRolePolicyDocument"] = {
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "sts:AssumeRole",
                "Principal": {"AWS": "arn:aws:sts::012345678901:assumed-role/Role/fixture-session"},
            }
        ]
    }
    graph, _ = collect(client)
    session = next(
        node for node in graph.principals if node.node_type == "sts.assumed_role_session"
    )
    role = next(node for node in graph.principals if node.node_type == "iam.role")
    assert session.principal_key != role.principal_key and session.scope.service == "sts"
    assert session.lifecycle_state == "unknown" and session.identity_strength == "scoped_reference"
    assert any(scope.service == "sts" for scope in graph.envelope.requested_scopes)
    assert (
        next(entry for entry in graph.envelope.coverage if entry.check == "sts.inventory").state
        == "partial"
    )
    assert not any(edge.relationship_type == "session_of_role" for edge in graph.relationships)


@pytest.mark.parametrize(
    "arn",
    [
        "arn:aws-cn:sts::012345678901:assumed-role/Role/Session",
        "arn:aws:sts::012345678901:assumed-role/Role/*",
        "arn:aws:sts::012345678901:root",
    ],
)
def test_invalid_or_wrong_partition_session_references_remain_incomplete(arn):
    client = IAM()
    client.page["RoleDetailList"][0]["AssumeRolePolicyDocument"] = {
        "Statement": [{"Effect": "Allow", "Action": "sts:AssumeRole", "Principal": {"AWS": arn}}]
    }
    graph, inventory = collect(client)
    assert not any(node.node_type == "sts.assumed_role_session" for node in graph.principals)
    assert inventory.graph.layer_coverage["trust_policies"].state == "partial"
