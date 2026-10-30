import base64
import importlib.util
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

spec = importlib.util.spec_from_file_location(
    "mesh_live_provider_verifier",
    Path(__file__).resolve().parents[2] / "scripts/verify_supabase_provider.py",
)
verifier = importlib.util.module_from_spec(spec)
# These tests use pure helpers only. The operator driver loads its protected
# runtime dotenv at import; keep real SMTP/provider credentials out of unit
# collection and prevent configured local services affecting unrelated tests.
with patch("dotenv.load_dotenv", return_value=False):
    spec.loader.exec_module(verifier)


@pytest.mark.parametrize(
    "epoch,expected",
    [
        (59, "287082"),
        (1111111109, "081804"),
        (1111111111, "050471"),
        (1234567890, "005924"),
        (2000000000, "279037"),
        (20000000000, "353130"),
    ],
)
def test_live_fixture_totp_uses_rfc6238_sha1_vectors(epoch, expected):
    secret = base64.b32encode(b"12345678901234567890").decode()
    assert verifier.totp(secret, epoch) == expected


@pytest.mark.parametrize(
    "status,payload,missing",
    [
        (404, {}, True),
        (400, {"statusCode": "404", "code": "NoSuchKey"}, True),
        (400, {"statusCode": 404, "error": "not_found"}, True),
        (400, {"statusCode": "403", "error": "not_found"}, False),
        (401, {"statusCode": "404", "code": "NoSuchKey"}, False),
        (400, {"message": "bad API key"}, False),
        (200, {}, False),
    ],
)
def test_cleanup_absence_never_confuses_missing_objects_and_rejected_credentials(
    status, payload, missing
):
    assert verifier.storage_object_missing(httpx.Response(status, json=payload)) is missing
