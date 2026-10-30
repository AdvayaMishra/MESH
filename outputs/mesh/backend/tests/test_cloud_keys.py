import hashlib
import json

import pytest
from app.cloud_keys import cloud_node_key

BASE = dict(
    organization_id="01234567-89ab-cdef-0123-456789abcdef",
    partition="aws",
    owner_namespace="012345678901",
    service="iam",
    region=None,
    node_type="iam.role",
    identity_kind="provider_uid",
    provider_identity="AROAFIXTURE123",
)


def test_key_matches_shared_wire_contract_and_canonical_uuid():
    values = [
        "mesh-cloud-identity-v1",
        BASE["organization_id"],
        "aws",
        "aws",
        "012345678901",
        "iam",
        "",
        "iam.role",
        "provider_uid",
        "AROAFIXTURE123",
    ]
    expected = (
        "cp1_" + hashlib.sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()
    )
    assert cloud_node_key(**BASE) == expected
    assert (
        cloud_node_key(**{**BASE, "organization_id": BASE["organization_id"].upper()}) == expected
    )
    assert len(expected) == 68


@pytest.mark.parametrize(
    "changes",
    [
        dict(organization_id="11234567-89ab-cdef-0123-456789abcdef"),
        dict(owner_namespace="112345678901"),
        dict(partition="aws-cn"),
        dict(provider_identity="AROAFIXTURE124"),
        dict(provider_identity="aroafixture123"),
    ],
)
def test_keys_isolate_tenants_accounts_partitions_and_reincarnations(changes):
    assert cloud_node_key(**{**BASE, **changes}) != cloud_node_key(**BASE)


def test_regional_assets_never_collide_across_regions():
    asset = {
        **BASE,
        "service": "ec2",
        "node_type": "ec2.security_group",
        "identity_kind": "scoped_native_id",
        "provider_identity": "sg-fixture",
        "region": "us-east-1",
    }
    assert cloud_node_key(**asset).startswith("ca1_")
    assert cloud_node_key(**asset) != cloud_node_key(**{**asset, "region": "us-west-2"})


@pytest.mark.parametrize(
    "changes",
    [
        dict(region="us-east-1"),
        dict(service="s3"),
        dict(node_type="future.node"),
        dict(owner_namespace="123"),
        dict(provider_identity=""),
        dict(provider_identity="x" * 257),
        dict(provider_identity="\ud800"),
        dict(provider_identity="role\nname"),
        dict(identity_kind="display_name"),
        dict(identity_kind="arn", provider_identity="arn:aws-cn:iam::012345678901:role/name"),
    ],
)
def test_unscoped_or_invalid_identities_fail_closed(changes):
    with pytest.raises(ValueError):
        cloud_node_key(**{**BASE, **changes})


@pytest.mark.parametrize(
    "arn",
    [
        "arn:aws:iam::999999999999:role/name",
        "arn:aws:iam:us-east-1:012345678901:role/name",
        "arn:aws:iam::012345678901:",
    ],
)
def test_arn_account_and_region_must_match_declared_scope(arn):
    with pytest.raises(ValueError):
        cloud_node_key(**{**BASE, "identity_kind": "arn", "provider_identity": arn})


def test_arn_casing_and_paths_are_preserved():
    first = {
        **BASE,
        "identity_kind": "arn",
        "provider_identity": "arn:aws:iam::012345678901:role/Team/Reader",
    }
    assert cloud_node_key(**first) != cloud_node_key(
        **{**first, "provider_identity": first["provider_identity"].lower()}
    )
