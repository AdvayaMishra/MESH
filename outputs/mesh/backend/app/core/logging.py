import json
import logging
from datetime import UTC, datetime


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        for field in (
            "request_id",
            "method",
            "status",
            "duration_ms",
            "exception_type",
            "worker_kind",
        ):
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        # Never include exception repr, request URLs, headers or bodies.
        return json.dumps(payload)


def configure() -> logging.Logger:
    logger = logging.getLogger("mesh")
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger
