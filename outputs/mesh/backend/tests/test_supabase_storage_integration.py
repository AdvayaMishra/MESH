import io
import os
from uuid import uuid4

import httpx
import pytest
from PIL import Image

URL = os.getenv("MESH_SUPABASE_TEST_URL", "")
ANON = os.getenv("MESH_SUPABASE_TEST_ANON_KEY", "")
SERVICE = os.getenv("MESH_SUPABASE_TEST_STORAGE_KEY", "")
USER = os.getenv("MESH_SUPABASE_TEST_USER_TOKEN", "")
pytestmark = pytest.mark.skipif(
    not all((URL, ANON, SERVICE, USER)),
    reason="Disposable Supabase Storage credentials not configured",
)


def test_live_private_bucket_denies_direct_clients():
    if os.getenv("MESH_SUPABASE_DISPOSABLE_TEST_PROJECT") != "true":
        pytest.fail("Explicit disposable Supabase test project authorization is required")
    key = "mesh-policy-test/" + uuid4().hex + "/fixture.png"
    output = io.BytesIO()
    Image.new("RGB", (2, 2), "white").save(output, "PNG")
    fixture = output.getvalue()
    service = {"apikey": SERVICE}
    if not SERVICE.startswith("sb_secret_"):
        service["Authorization"] = "Bearer " + SERVICE
    with httpx.Client(
        base_url=URL.rstrip("/") + "/storage/v1/", timeout=15, follow_redirects=False
    ) as client:
        profile = client.get(
            URL.rstrip("/") + "/auth/v1/user",
            headers={"apikey": ANON, "Authorization": "Bearer " + USER},
        )
        profile.raise_for_status()
        assert profile.json().get("email_confirmed_at")
        bucket = client.get("bucket/mesh-identity", headers=service)
        bucket.raise_for_status()
        assert bucket.json()["public"] is False
        assert bucket.json()["file_size_limit"] == 2097152
        assert set(bucket.json()["allowed_mime_types"]) == {"image/png", "image/jpeg"}
        response = client.post(
            "object/mesh-identity/" + key,
            headers={**service, "Content-Type": "image/png"},
            content=fixture,
        )
        response.raise_for_status()
        try:
            for credential in (ANON, USER):
                client_headers = {"apikey": ANON}
                if credential != ANON or not ANON.startswith("sb_publishable_"):
                    client_headers["Authorization"] = "Bearer " + credential
                direct = client.get(
                    "object/mesh-identity/" + key,
                    headers=client_headers,
                )
                assert direct.status_code in {400, 401, 403, 404}
                assert direct.content != fixture
                for method, payload in (("POST", fixture), ("PUT", fixture)):
                    write = client.request(
                        method,
                        "object/mesh-identity/" + key,
                        headers={**client_headers, "Content-Type": "image/png"},
                        content=payload,
                    )
                    assert write.status_code in {400, 401, 403, 404, 409}
                signing = client.post(
                    "object/sign/mesh-identity/" + key,
                    headers=client_headers,
                    json={"expiresIn": 60},
                )
                assert signing.status_code in {400, 401, 403, 404}
                removal = client.request(
                    "DELETE",
                    "object/mesh-identity",
                    headers=client_headers,
                    json={"prefixes": [key]},
                )
                # Storage may return success with an empty list for invisible objects.
                assert removal.status_code in {200, 400, 401, 403, 404}
                retained = client.get("object/mesh-identity/" + key, headers=service)
                retained.raise_for_status()
                assert retained.content == fixture
            signed = client.post(
                "object/sign/mesh-identity/" + key,
                headers=service,
                json={"expiresIn": 60},
            )
            signed.raise_for_status()
            path = signed.json()["signedURL"]
            assert path.startswith("/object/sign/mesh-identity/")
            download = client.get(URL.rstrip("/") + "/storage/v1" + path)
            download.raise_for_status()
            assert download.content == fixture
        finally:
            cleanup = client.request(
                "DELETE", "object/mesh-identity", headers=service, json={"prefixes": [key]}
            )
            cleanup.raise_for_status()
