"""Fail-closed primitives; network fetching is deliberately not exposed."""

import hashlib
import hmac
import ipaddress
import re
from urllib.parse import urlsplit


def normalize_domain(value: str) -> str:
    parsed = urlsplit(value if "://" in value else "https://" + value)
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port not in {None, 443}
    ):
        raise ValueError("HTTPS domain without credentials required")
    host = (parsed.hostname or "").rstrip(".").encode("idna").decode("ascii").lower()
    if not re.fullmatch(
        r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", host
    ):
        raise ValueError("Public DNS name required")
    return host


def validate_addresses(addresses: list[str]) -> None:
    if not addresses:
        raise ValueError("No DNS answers")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global or (isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped):
            raise ValueError("Non-public destinations forbidden")


def verify_webhook(body: bytes, signature: str, secret: bytes) -> bool:
    if len(secret) < 32 or len(body) > 1048576:
        return False
    expected = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def sanitized_scanner_finding(scanner: str, raw: dict) -> dict:
    # Evidence and scanner prose can contain secret values. Persist only bounded location/rule data.
    path = str(raw.get("path", ""))
    if path.startswith(("/", "\\")) or ".." in path.replace("\\", "/").split("/") or ":" in path:
        raise ValueError("Unsafe finding path")
    severity = str(raw.get("severity", "unknown")).lower()
    finding = {
        "scanner": scanner,
        "rule_id": str(raw.get("rule_id", "unknown"))[:200],
        "file_path": path[:500],
        "line": max(1, int(raw.get("line", 1))),
        "severity": severity
        if severity in {"critical", "high", "medium", "low", "info"}
        else "info",
    }

    column = raw.get("column")
    if column is not None:
        if type(column) is not int or not 1 <= column <= 2147483647:
            raise ValueError("Invalid finding column")
        finding["column"] = column
    return finding
