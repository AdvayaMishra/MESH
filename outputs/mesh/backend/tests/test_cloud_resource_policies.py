import json

import pytest
from app.cloud_context_schema import Snapshot
from app.cloud_identity import AWSAccountIdentity
from app.cloud_normalizer import CloudNormalizer
from app.cloud_resource_policies import S3PolicyInventory
from botocore.exceptions import ClientError
from conftest import ORG_A


class S3:
    def get_bucket_policy(self, **kwargs):
        return {
            "Policy": json.dumps(
                {
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": ["s3:GetObject"],
                            "Resource": "arn:aws:s3:::fixture/*",
                            "Principal": {"AWS": "arn:aws:iam::999999999999:role/Reader"},
                            "Condition": {"StringEquals": {"private": "DO_NOT_RETAIN"}},
                        }
                    ]
                }
            )
        }


def collect(client, failed=False):
    graph = CloudNormalizer(
        ORG_A, AWSAccountIdentity.from_role("arn:aws:iam::012345678901:role/mesh-reader"), {}, 200
    )
    node = graph.observe("s3", "s3.bucket", native="fixture")
    collector = S3PolicyInventory(client, graph, lambda: None)
    collector.bucket("fixture", node)
    collector.finish(failed)
    return Snapshot.model_validate(graph.finish([], ["Synthetic fixture only"]))


def test_s3_policy_retains_statement_and_external_reference_without_access_claim():
    graph = collect(S3())
    permission = graph.permissions[0]
    assert permission.policy_kind == "resource" and permission.principal_key is None
    assert permission.subject_ref.kind == "asset" and permission.condition_state == "present"
    edge = graph.relationships[0]
    assert edge.relationship_type == "resource_policy_references"
    assert edge.basis == "policy_derived" and edge.effective_decision == "not_evaluated"
    assert graph.principals[0].ownership == "external_account"
    assert "DO_NOT_RETAIN" not in graph.model_dump_json()
    assert (
        next(item for item in graph.envelope.coverage if item.check == "s3.resource_policies").state
        == "complete"
    )


@pytest.mark.parametrize(
    "code,expected",
    [("NoSuchBucketPolicy", "complete"), ("AccessDenied", "partial"), ("NoSuchBucket", "partial")],
)
def test_absent_policy_is_distinct_from_denied_or_deleted_bucket(code, expected):
    class Failed(S3):
        def get_bucket_policy(self, **kwargs):
            raise ClientError(
                {"Error": {"Code": code, "Message": "DO_NOT_RETAIN"}}, "GetBucketPolicy"
            )

    graph = collect(Failed())
    assert not graph.permissions and not graph.relationships
    coverage = next(
        item for item in graph.envelope.coverage if item.check == "s3.resource_policies"
    )
    assert coverage.state == expected
    assert "DO_NOT_RETAIN" not in graph.model_dump_json()


def test_incomplete_bucket_inventory_cannot_claim_all_resource_policies_collected():
    graph = collect(S3(), True)
    coverage = next(
        item for item in graph.envelope.coverage if item.check == "s3.resource_policies"
    )
    assert coverage.state == "partial" and coverage.truncated
