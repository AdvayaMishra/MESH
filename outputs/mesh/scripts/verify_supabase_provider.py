"""Live Supabase provider acceptance using one generated, temporary Auth user.

No email is sent; administrative link generation supplies real confirmation and
recovery tokens. Application handlers are called directly, not through a running
HTTP stack. Provider users/objects are deleted; application DB changes roll back.
"""

import base64
import hashlib
import hmac
import io
import json
import re
import secrets
import struct
import sys
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from uuid import uuid4

import httpx
from dotenv import load_dotenv
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from PIL import Image
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.requests import Request

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))
from app import mfa_api  # noqa: E402
from app.account_api import PasswordInput, update_password  # noqa: E402
from app.api import logout, verify_email  # noqa: E402
from app.auth import identity  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.db import assert_runtime_role  # noqa: E402
from app.documents import PrivateStorage, validate_image  # noqa: E402
from app.identity_provider import Login, Refresh, SupabaseAuth, Verify  # noqa: E402
from app.sessions import track_identity  # noqa: E402


class ProviderFailure(Exception):
    def __init__(self, status, code=None):
        self.status, self.code = status, code


def totp(secret, epoch=None):
    secret += "=" * (-len(secret) % 8)
    key = base64.b32decode(secret.upper())
    digest = hmac.new(
        key, struct.pack(">Q", int(time.time() if epoch is None else epoch) // 30), hashlib.sha1
    ).digest()
    offset = digest[-1] & 15
    return str((struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1000000).zfill(
        6
    )


def storage_object_missing(response: httpx.Response) -> bool:
    if response.status_code == 404:
        return True
    if response.status_code != 400:
        return False
    try:
        data = response.json()
    except ValueError:
        return False
    # Storage sometimes wraps an object 404 inside HTTP 400. Rejected API keys
    # and generic errors do not prove that fixture cleanup succeeded.
    return (
        isinstance(data, dict)
        and str(data.get("statusCode")) == "404"
        and (data.get("code") == "NoSuchKey" or data.get("error") == "not_found")
    )


def verify(after_mfa=None):
    config = settings()
    secret = config.supabase_storage_key
    if not secret:
        raise RuntimeError("Backend key is missing")
    admin_headers = {"apikey": secret.get_secret_value()}
    if not secret.get_secret_value().startswith("sb_secret_"):
        admin_headers["Authorization"] = "Bearer " + secret.get_secret_value()
    run_id = uuid4().hex
    email = "mesh-verification-" + run_id + "@mesh.invalid"
    password = secrets.token_urlsafe(32)
    user_id = None
    object_key = str(uuid4()) + "/" + str(uuid4()) + "/" + str(uuid4())
    ledger = ROOT.parents[1] / "work/supabase-live-fixture.json"
    assert not ledger.exists(), (
        "Unresolved fixture ledger exists; recover it before creating another user"
    )
    ledger.write_text(
        json.dumps({"run_id": run_id, "email": email, "object_key": object_key, "user_id": None}),
        encoding="utf-8",
    )
    checks, pending = {}, []
    stage = "initialize"
    engine = create_engine(config.database_url)
    report = {
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "checks": checks,
        "pending": pending,
    }
    storage = PrivateStorage()
    object_attempted = False
    failure = None
    provider_clock_offset = 0.0
    try:
        with httpx.Client(timeout=20, follow_redirects=False) as client, Session(engine) as db:

            def admin(method, path, data=None):
                nonlocal provider_clock_offset
                response = client.request(
                    method,
                    config.supabase_url.rstrip("/") + "/auth/v1/" + path,
                    headers=admin_headers,
                    json=data,
                )
                if response.headers.get("date"):
                    provider_clock_offset = (
                        parsedate_to_datetime(response.headers["date"]).timestamp() - time.time()
                    )
                if response.status_code >= 400:
                    try:
                        code = response.json().get("error_code") or response.json().get("code")
                        code = (
                            code
                            if isinstance(code, str) and re.fullmatch(r"[a-zA-Z0-9_]{1,80}", code)
                            else None
                        )
                    except ValueError:
                        code = None
                    raise ProviderFailure(response.status_code, code)
                return response.json() if response.content else {}

            def who(tokens):
                return identity(
                    HTTPAuthorizationCredentials(scheme="Bearer", credentials=tokens.access_token)
                )

            def observe(person):
                track_identity(
                    db,
                    person,
                    Request(
                        {
                            "type": "http",
                            "headers": [(b"user-agent", b"MESH live synthetic verification")],
                            "client": ("127.0.0.1", 0),
                        }
                    ),
                )

            assert_runtime_role(db)
            stage = "create_unconfirmed_fixture_user"
            user = admin(
                "POST",
                "admin/users",
                {
                    "email": email,
                    "password": password,
                    "email_confirm": False,
                    "user_metadata": {"mesh_verification_fixture": run_id},
                },
            )
            user_id = user["id"]
            ledger.write_text(
                json.dumps(
                    {"run_id": run_id, "email": email, "object_key": object_key, "user_id": user_id}
                ),
                encoding="utf-8",
            )
            assert not user.get("email_confirmed_at")
            checks["temporary_unconfirmed_auth_user_created"] = "passed"
            stage = "generate_signup_confirmation"
            link = admin(
                "POST",
                "admin/generate_link",
                {"type": "signup", "email": email, "password": password},
            )
            stage = "verify_signup_otp"
            tokens = verify_email(
                Verify(email=email, token=SecretStr(link["email_otp"]), type="signup")
            )
            person = who(tokens)
            assert person.user_id == user_id
            observe(person)
            checks["real_signup_confirmation_otp_and_asymmetric_identity"] = "passed"
            stage = "password_login"
            try:
                tokens = SupabaseAuth().login(
                    Login(
                        email=email,
                        password=SecretStr(password),
                        captcha_token=SecretStr("mesh-synthetic-admin-fixture"),
                    )
                )
                assert who(tokens).user_id == user_id
                checks["real_password_login"] = "passed"
            except HTTPException as exc:
                if exc.status_code != 401:
                    raise
                pending.append(
                    "Password login rejected; CAPTCHA or provider login policy needs separate verification."
                )
            stage = "refresh_session"
            tokens = SupabaseAuth().refresh(Refresh(refresh_token=SecretStr(tokens.refresh_token)))
            person = who(tokens)
            observe(person)
            checks["real_refresh_and_session_observation"] = "passed"
            stage = "totp_enroll"
            enrollment = mfa_api.enroll(
                mfa_api.EnrollmentInput(friendly_name="MESH temporary verification"),
                person,
                "Bearer " + tokens.access_token,
            )
            stage = "totp_challenge"
            challenge = mfa_api.challenge(enrollment.id, person, "Bearer " + tokens.access_token)
            stage = "totp_verify"
            admin("GET", "admin/users/" + user_id)
            assert abs(provider_clock_offset) < 600
            report["test_clock_offset_seconds"] = round(provider_clock_offset)
            tokens = mfa_api.verify(
                enrollment.id,
                mfa_api.VerifyInput(
                    challenge_id=challenge.id,
                    code=SecretStr(
                        totp(enrollment.totp.secret, time.time() + provider_clock_offset)
                    ),
                ),
                person,
                db,
                "Bearer " + tokens.access_token,
            )
            person = who(tokens)
            assert person.aal == "aal2"
            assert any(
                factor.id == enrollment.id and factor.status == "verified"
                for factor in mfa_api.factors(tokens.access_token)
            )
            checks["real_totp_enrollment_challenge_verification_aal2"] = "passed"
            if after_mfa is not None:
                after_mfa(db, person, tokens, checks)
            stage = "private_storage_fixture"
            output = io.BytesIO()
            Image.new("RGB", (4, 4), "white").save(output, "PNG")
            image = output.getvalue()
            validate_image(image, "image/png")
            object_attempted = True
            storage.upload(object_key, image, "image/png")
            signed = storage.sign(object_key)
            download = client.get(signed)
            assert download.status_code == 200 and download.content == image
            checks["real_private_storage_upload_sign_download"] = "passed"
            for label, headers in [
                ("public", {"apikey": config.supabase_anon_key}),
                (
                    "user",
                    {
                        "apikey": config.supabase_anon_key,
                        "Authorization": "Bearer " + tokens.access_token,
                    },
                ),
            ]:
                base = config.supabase_url.rstrip("/") + "/storage/v1/"
                direct = client.get(base + "object/mesh-identity/" + object_key, headers=headers)
                assert direct.status_code in {400, 401, 403, 404} and direct.content != image
                signing = client.post(
                    base + "object/sign/mesh-identity/" + object_key,
                    headers=headers,
                    json={"expiresIn": 60},
                )
                assert signing.status_code in {400, 401, 403, 404}
                for method in ("POST", "PUT"):
                    write = client.request(
                        method,
                        base + "object/mesh-identity/" + object_key,
                        headers={**headers, "Content-Type": "image/png"},
                        content=image,
                    )
                    assert write.status_code in {400, 401, 403, 404, 409}
                client.request(
                    "DELETE",
                    base + "object/mesh-identity",
                    headers=headers,
                    json={"prefixes": [object_key]},
                )
                assert client.get(storage.sign(object_key)).content == image
                checks["real_" + label + "_storage_read_write_sign_delete_denied"] = "passed"
            stage = "totp_remove"
            removed = mfa_api.unenroll(enrollment.id, person, db, "Bearer " + tokens.access_token)
            assert removed.requires_new_login
            assert not any(
                factor.id == enrollment.id for factor in mfa_api.factors(tokens.access_token)
            )
            checks["real_totp_removal_and_local_session_revocation"] = "passed"
            stage = "recovery_otp"
            link = admin("POST", "admin/generate_link", {"type": "recovery", "email": email})
            tokens = verify_email(
                Verify(email=email, token=SecretStr(link["email_otp"]), type="recovery")
            )
            person = who(tokens)
            observe(person)
            stage = "recovery_password_update"
            new_password = secrets.token_urlsafe(32)
            update_password(
                PasswordInput(password=SecretStr(new_password)),
                person,
                db,
                "Bearer " + tokens.access_token,
            )
            checks["real_recovery_otp_and_password_update"] = "passed"
            stage = "new_password_login"
            if checks.get("real_password_login") == "passed":
                try:
                    SupabaseAuth().login(
                        Login(
                            email=email,
                            password=SecretStr(password),
                            captcha_token=SecretStr("mesh-synthetic-admin-fixture"),
                        )
                    )
                except HTTPException as exc:
                    assert exc.status_code == 401
                else:
                    raise AssertionError("Previous password remained usable after recovery")
                checks["previous_password_rejected_after_recovery"] = "passed"
                tokens = SupabaseAuth().login(
                    Login(
                        email=email,
                        password=SecretStr(new_password),
                        captcha_token=SecretStr("mesh-synthetic-admin-fixture"),
                    )
                )
                person = who(tokens)
                observe(person)
                checks["real_new_password_login"] = "passed"
            stage = "logout"
            result = logout(person, db, "Bearer " + tokens.access_token)
            assert result["provider_logout"] == "confirmed"
            try:
                SupabaseAuth().refresh(Refresh(refresh_token=SecretStr(tokens.refresh_token)))
            except HTTPException as exc:
                assert exc.status_code == 401
            else:
                raise AssertionError("Provider refresh remained usable after global logout")
            checks["provider_refresh_rejected_after_global_logout"] = "passed"
            try:
                observe(person)
            except HTTPException as exc:
                assert exc.status_code == 401
            else:
                raise AssertionError("MESH observed session was not denied after logout")
            checks["real_provider_logout_and_immediate_mesh_denial"] = "passed"
            db.rollback()
            checks["all_application_session_fixtures_rolled_back"] = "passed"
    except Exception as exc:
        failure = {"stage": stage, "type": type(exc).__name__}
        if isinstance(exc, ProviderFailure):
            failure.update(status=exc.status, code=exc.code)
        elif isinstance(exc, HTTPException):
            failure["status"] = exc.status_code
        report["failure"] = failure
    finally:
        engine.dispose()
        cleanup = {}
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            if object_attempted:
                try:
                    storage.delete(object_key)
                    absence = client.get(
                        config.supabase_url.rstrip("/")
                        + "/storage/v1/object/mesh-identity/"
                        + object_key,
                        headers=admin_headers,
                    )
                    assert storage_object_missing(absence)
                    cleanup["storage_object_removed"] = True
                except Exception:
                    cleanup["storage_object_removed"] = False
            if user_id:
                try:
                    url = config.supabase_url.rstrip("/") + "/auth/v1/admin/users/" + user_id
                    result = client.delete(url, headers=admin_headers)
                    assert result.status_code in {200, 204}
                    assert client.get(url, headers=admin_headers).status_code == 404
                    cleanup["temporary_auth_user_removed"] = True
                except Exception:
                    cleanup["temporary_auth_user_removed"] = False
        report["cleanup"] = cleanup
        if (
            user_id
            and cleanup.get("temporary_auth_user_removed")
            and (not object_attempted or cleanup.get("storage_object_removed"))
        ):
            ledger.unlink()
        report["limitations"] = [
            "Confirmation/recovery tokens generated through authorized admin API; inbox delivery and CAPTCHA are not validated.",
            "Synthetic TOTP generator aligns with HTTPS provider Date because host clock is ahead; OS clock and production JWT verification were not changed.",
            "Core provider checks call handlers directly; the optional combined-document callback separately exercises real ASGI middleware, Redis, PostgreSQL RLS, ClamAV and private Storage. See combined_* checks for whether it ran.",
            "Only synthetic documents collected; default core Storage checks are separate from ClamAV unless the combined-document callback ran.",
        ]
        report["passed"] = failure is None and not pending and all(cleanup.values())
        (ROOT / "docs/supabase-provider-results.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
    return report


if __name__ == "__main__":
    try:
        report = verify()
    except Exception as exc:
        print(json.dumps({"failed": type(exc).__name__}))
        raise SystemExit(1) from None
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
