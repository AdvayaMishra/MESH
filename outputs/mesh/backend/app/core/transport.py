"""Pure transport policy checks shared by runtime and deployment validation."""

import ipaddress
from urllib.parse import parse_qs, urlsplit


def loopback_host(value: str) -> bool:
    value = value.rstrip(".").lower()
    if value == "localhost":
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def authenticated_redis_tls(value: str) -> bool:
    try:
        redis = urlsplit(value)
        options = parse_qs(redis.query, keep_blank_values=True)
        return bool(
            redis.scheme == "rediss"
            and redis.hostname
            and redis.password
            and (redis.port is None or redis.port > 0)
            and options.get("ssl_cert_reqs", ["required"]) == ["required"]
            and len(options.get("ssl_check_hostname", ["true"])) == 1
            and options.get("ssl_check_hostname", ["true"])[0].lower() in {"true", "1"}
        )
    except ValueError:
        return False
