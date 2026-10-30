import pytest
from app.core.config import Settings
from pydantic import ValidationError


def test_configuration_errors_and_representations_do_not_expose_database_passwords():
    secret = "FIXTURE_PRIVATE_PASSWORD"
    with pytest.raises(ValidationError) as exc:
        Settings(
            _env_file=None,
            environment="production",
            test_mode=False,
            supabase_url="https://identity.example.org",
            require_privileged_mfa=True,
            auth_rate_secret="a" * 48,
            redis_url="rediss://default:fixture@redis.example.com:6380/0",
            database_url=f"postgresql+psycopg://user:{secret}@database.example.org/mesh",
        )
    assert secret not in str(exc.value)
    assert "verified TLS" in str(exc.value)
    config = Settings(
        _env_file=None, database_url=f"postgresql://user:{secret}@database.example.org/mesh"
    )
    assert config.database_url.startswith("postgresql+psycopg://")
    assert secret not in repr(config)


def test_production_accepts_an_explicit_verified_postgres_connection():
    config = Settings(
        _env_file=None,
        environment="production",
        test_mode=False,
        supabase_url="https://identity.example.org",
        require_privileged_mfa=True,
        auth_rate_secret="a" * 48,
        redis_url="rediss://default:fixture@redis.example.com:6380/0",
        database_url="postgresql+psycopg://runtime:fixture@database.example.org/mesh?sslmode=verify-full&sslrootcert=system",
    )
    assert config.environment == "production"


@pytest.mark.parametrize(
    "redis",
    [
        "redis://default:private-password@cache.example.com:6379/0",
        "rediss://cache.example.com:6380/0",
        "rediss://default:private-password@cache.example.com:6380/0?ssl_cert_reqs=none",
        "rediss://default:private-password@cache.example.com:6380/0?ssl_check_hostname=false",
    ],
)
def test_production_redis_fails_closed_for_plaintext_unauthenticated_or_unverified_tls(redis):
    with pytest.raises(ValidationError) as error:
        Settings(
            _env_file=None,
            environment="production",
            test_mode=False,
            supabase_url="https://identity.example.com",
            require_privileged_mfa=True,
            auth_rate_secret="a" * 48,
            database_url="postgresql+psycopg://runtime:fixture@database.example.com/mesh?sslmode=verify-full&sslrootcert=system",
            redis_url=redis,
        )
    assert "Production Redis requires authenticated TLS" in str(error.value)
    assert "private-password" not in str(error.value)
