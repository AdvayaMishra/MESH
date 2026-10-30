"""Actual loopback HTTP + Redis + hosted PostgreSQL/Supabase acceptance.

Creates two temporary Auth users and self-owned session rows only. Cleanup uses
administrator DB authority restricted to those users and this unique client hint.
No organization/business/audit rows are created or removed. Redis and API stop.
"""

import argparse
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import psycopg
from dotenv import dotenv_values
from redis import Redis

ROOT = Path(__file__).resolve().parents[1]


def verify(redis_executable: Path):
    assert redis_executable.is_absolute() and redis_executable.is_file()
    config = {k: v for k, v in dotenv_values(ROOT / ".env").items() if v is not None}
    setup = dotenv_values(
        os.getenv("MESH_SUPABASE_SETUP_FILE", str(ROOT.parents[1] / "work/supabase-setup.env"))
    )
    backend_key = config["SUPABASE_STORAGE_KEY"]
    admin_headers = {"apikey": backend_key}
    if not backend_key.startswith("sb_secret_"):
        admin_headers["Authorization"] = "Bearer " + backend_key
    base = config["SUPABASE_URL"].rstrip("/")
    run_id = uuid4().hex
    hint = "MESH HTTP runtime fixture " + run_id
    ledger = ROOT.parents[1] / "work/http-runtime-fixtures.json"
    assert not ledger.exists(), "An unresolved runtime fixture requires cleanup before another run"
    fixture_users = []
    ledger.write_text(
        json.dumps({"run_id": run_id, "client_hint": hint, "users": fixture_users}),
        encoding="utf-8",
    )
    checks = {}
    report = {"verified_at_utc": datetime.now(UTC).isoformat(), "checks": checks}
    stage = "start_redis"
    cleanup = {}
    api_process = redis_process = None
    redis_password = secrets.token_urlsafe(32)
    with tempfile.TemporaryDirectory(prefix="mesh-http-runtime-") as folder:
        work = Path(folder)
        redis_config = work / "redis.conf"
        redis_config.write_text(
            f'bind 127.0.0.1\nport 16379\nprotected-mode yes\nrequirepass {redis_password}\nsave ""\nappendonly no\nmaxmemory 64mb\nmaxmemory-policy noeviction\n',
            encoding="utf-8",
        )
        try:
            redis_process = subprocess.Popen(
                [str(redis_executable), redis_config.name],
                cwd=work,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            redis = Redis(
                host="127.0.0.1",
                port=16379,
                password=redis_password,
                socket_connect_timeout=0.5,
                socket_timeout=2,
            )
            for _ in range(40):
                if redis_process.poll() is not None:
                    raise RuntimeError("Redis exited before readiness")
                try:
                    if redis.ping():
                        break
                except Exception:
                    pass
                time.sleep(0.25)
            else:
                raise RuntimeError("Redis startup timed out")
            assert (
                redis.eval(
                    "local c=redis.call('INCR',KEYS[1]); redis.call('EXPIRE',KEYS[1],120); return c",
                    1,
                    "mesh:runtime-fixture",
                )
                == 1
            )
            assert redis.ttl("mesh:runtime-fixture") > 0
            checks["real_redis_ping_lua_and_expiry"] = "passed"
            stage = "start_http_api"
            environment = {
                **os.environ,
                **config,
                "PYTHONPATH": str(ROOT / "backend"),
                "TEST_MODE": "false",
                "REDIS_URL": "redis://:" + redis_password + "@127.0.0.1:16379/0",
            }
            api_process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "18765",
                    "--no-access-log",
                ],
                cwd=ROOT,
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            with httpx.Client(
                base_url="http://127.0.0.1:18765",
                headers={"User-Agent": hint},
                timeout=30,
                follow_redirects=False,
            ) as client:
                for _ in range(80):
                    if api_process.poll() is not None:
                        raise RuntimeError("API exited before readiness")
                    try:
                        if client.get("/health/live", timeout=0.5).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.25)
                else:
                    raise RuntimeError("API startup timed out")
                assert client.get("/health/ready").status_code == 200
                assert client.get("/openapi.json").json() == json.loads(
                    (ROOT / "docs/openapi.json").read_text(encoding="utf-8")
                )
                checks["actual_http_liveness_readiness_and_exported_contract"] = "passed"
                anonymous = client.get("/api/v1/users/me/sessions")
                assert anonymous.status_code == 401
                assert anonymous.headers["Cache-Control"] == "no-store"
                assert anonymous.headers["X-Content-Type-Options"] == "nosniff"
                UUID(anonymous.headers["X-Request-ID"])
                checks["http_auth_denial_and_security_headers"] = "passed"
                sessions = []
                passwords = []
                stage = "create_confirmed_fixture_users"
                for index in range(2):
                    email = f"mesh-http-{run_id}-{index}@mesh.invalid"
                    password = secrets.token_urlsafe(32)
                    response = client.post(
                        base + "/auth/v1/admin/users",
                        headers=admin_headers,
                        json={
                            "email": email,
                            "password": password,
                            "email_confirm": True,
                            "user_metadata": {"mesh_http_fixture": run_id},
                        },
                    )
                    assert response.status_code in {200, 201}
                    user = response.json()
                    assert user["email"] == email
                    fixture_users.append({"id": user["id"], "email": email})
                    ledger.write_text(
                        json.dumps({"run_id": run_id, "client_hint": hint, "users": fixture_users}),
                        encoding="utf-8",
                    )
                    passwords.append(password)
                    stage = "http_login_and_sessions"
                    response = client.post(
                        "/api/v1/auth/login",
                        json={
                            "email": email,
                            "password": password,
                            "captcha_token": "mesh-synthetic-admin-fixture",
                        },
                    )
                    assert response.status_code == 200
                    tokens = response.json()
                    response = client.get(
                        "/api/v1/users/me/sessions",
                        headers={"Authorization": "Bearer " + tokens["access_token"]},
                    )
                    assert response.status_code == 200
                    own = response.json()
                    assert len(own) == 1 and own[0]["current"]
                    sessions.append({"tokens": tokens, "row_id": own[0]["id"]})
                checks["actual_http_password_login_and_session_persistence"] = "passed"
                first, second = sessions
                bearer = {"Authorization": "Bearer " + first["tokens"]["access_token"]}
                response = client.delete(
                    "/api/v1/users/me/sessions/" + second["row_id"], headers=bearer
                )
                assert response.status_code == 404
                mine = client.get("/api/v1/users/me/sessions", headers=bearer).json()
                assert all(row["id"] != second["row_id"] for row in mine)
                assert (
                    client.get(
                        "/api/v1/organizations/current",
                        headers={**bearer, "X-Organization-ID": str(uuid4())},
                    ).status_code
                    == 403
                )
                checks["actual_http_self_session_and_tenant_authorization"] = "passed"
                stage = "http_totp_enrollment"
                response = client.post(
                    "/api/v1/auth/mfa/enroll",
                    headers=bearer,
                    json={"friendly_name": "MESH HTTP temporary fixture"},
                )
                assert response.status_code == 201
                enrollment = response.json()
                factor_id = enrollment["id"]
                response = client.post(
                    "/api/v1/auth/mfa/factors/" + factor_id + "/challenge", headers=bearer
                )
                assert response.status_code == 200
                challenge = response.json()
                clock = client.get(
                    base + "/auth/v1/admin/users/" + fixture_users[0]["id"], headers=admin_headers
                )
                assert clock.status_code == 200
                from verify_supabase_provider import totp

                epoch = parsedate_to_datetime(clock.headers["date"]).timestamp()
                stage = "http_totp_verification"
                response = client.post(
                    "/api/v1/auth/mfa/factors/" + factor_id + "/verify",
                    headers=bearer,
                    json={
                        "challenge_id": challenge["id"],
                        "code": totp(enrollment["totp"]["secret"], epoch),
                    },
                )
                assert response.status_code == 200
                first["tokens"] = response.json()
                bearer = {"Authorization": "Bearer " + first["tokens"]["access_token"]}
                response = client.delete("/api/v1/auth/mfa/factors/" + factor_id, headers=bearer)
                assert response.status_code == 200 and response.json()["requires_new_login"]
                assert client.get("/api/v1/users/me/sessions", headers=bearer).status_code == 401
                checks["actual_http_totp_and_factor_removal_session_denial"] = "passed"
                stage = "http_logout"
                response = client.post(
                    "/api/v1/auth/login",
                    json={
                        "email": fixture_users[0]["email"],
                        "password": passwords[0],
                        "captcha_token": "mesh-synthetic-admin-fixture",
                    },
                )
                assert response.status_code == 200
                tokens = response.json()
                bearer = {"Authorization": "Bearer " + tokens["access_token"]}
                assert client.get("/api/v1/users/me/sessions", headers=bearer).status_code == 200
                response = client.post("/api/v1/auth/logout", headers=bearer)
                assert (
                    response.status_code == 200
                    and response.json()["provider_logout"] == "confirmed"
                )
                assert client.get("/api/v1/users/me/sessions", headers=bearer).status_code == 401
                response = client.post(
                    "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
                )
                assert response.status_code == 401
                checks["actual_http_logout_local_denial_and_provider_refresh_revocation"] = "passed"
                stage = "http_limits"
                response = client.post(
                    "/api/v1/auth/login",
                    content=b"x" * 262145,
                    headers={"Content-Type": "application/json"},
                )
                assert (
                    response.status_code == 413 and response.headers["Cache-Control"] == "no-store"
                )
                for _ in range(41):
                    response = client.post(
                        "/api/v1/auth/login", json={"email": "throttle-" + run_id + "@mesh.invalid"}
                    )
                    if response.status_code == 429:
                        break
                    assert response.status_code == 422
                assert response.status_code == 429 and response.headers["Retry-After"] == "60"
                keys = list(redis.scan_iter("mesh:auth:*"))
                assert keys and all(b"@" not in key for key in keys)
                assert all(0 < redis.ttl(key) <= 120 for key in keys)
                checks["actual_http_body_bound_and_private_account_redis_throttling"] = "passed"
                stage = "redis_outage"
                redis_process.terminate()
                redis_process.wait(timeout=15)
                assert client.get("/health/ready").status_code == 503
                assert client.get("/api/v1/users/me/sessions").status_code == 503
                checks["real_redis_outage_fails_closed"] = "passed"
        except Exception as exc:
            report["failure"] = {"stage": stage, "type": type(exc).__name__}
        finally:
            for process in (api_process, redis_process):
                if process and process.poll() is None:
                    process.terminate()
                    process.wait(timeout=15)
            try:
                with psycopg.connect(
                    host=setup["SUPABASE_DB_HOST"],
                    port=5432,
                    dbname="postgres",
                    user="postgres." + setup["SUPABASE_PROJECT_REF"],
                    password=setup["SUPABASE_DB_PASSWORD"],
                    sslmode="verify-full",
                    sslrootcert=str(ROOT / "supabase/supabase-ca.crt"),
                    connect_timeout=15,
                ) as db:
                    for user in fixture_users:
                        UUID(user["id"])
                        db.execute(
                            "DELETE FROM public.identity_sessions WHERE user_id=%s AND client_hint=%s",
                            (user["id"], hint),
                        )
                        assert (
                            db.execute(
                                "SELECT count(*) FROM public.identity_sessions WHERE user_id=%s",
                                (user["id"],),
                            ).fetchone()[0]
                            == 0
                        )
                cleanup["own_temporary_session_rows_removed"] = True
            except Exception:
                cleanup["own_temporary_session_rows_removed"] = False
            try:
                with httpx.Client(timeout=20, follow_redirects=False) as client:
                    for user in fixture_users:
                        url = base + "/auth/v1/admin/users/" + user["id"]
                        existing = client.get(url, headers=admin_headers)
                        assert existing.status_code == 404 or (
                            existing.json()["user_metadata"]["mesh_http_fixture"] == run_id
                            and existing.json()["email"] == user["email"]
                        )
                        if existing.status_code != 404:
                            assert client.delete(url, headers=admin_headers).status_code in {
                                200,
                                204,
                            }
                        assert client.get(url, headers=admin_headers).status_code == 404
                cleanup["own_temporary_auth_users_removed"] = True
            except Exception:
                cleanup["own_temporary_auth_users_removed"] = False
            report["cleanup"] = cleanup
            report["passed"] = "failure" not in report and all(cleanup.values())
            report["limitations"] = [
                "Development-only community MSYS2 Redis build; production Linux containers not run.",
                "Confirmed test identities created administratively; real inbox delivery and CAPTCHA are not validated.",
                "No organization, business or audit rows created; cleanup deletes only this run's generated users and matching self-session observations.",
                "Synthetic TOTP codes use provider HTTPS time because host clock is ahead.",
            ]
            if all(cleanup.values()):
                ledger.unlink()
    (ROOT / "docs/http-runtime-results.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--redis-executable", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = verify(args.redis_executable)
    except Exception as exc:
        print(json.dumps({"failed": type(exc).__name__}))
        raise SystemExit(1) from None
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
