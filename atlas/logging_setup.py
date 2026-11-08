"""Logging configuration.

The default is a compact human-readable line. Set ``ATLAS_LOG_JSON=1`` for
newline-delimited JSON, which is what container and CI environments expect.
Request-scoped fields arrive through ``extra`` and are ignored by the text
formatter.
"""
from __future__ import annotations

import json
import logging
import os
import time


REQUEST_FIELDS = ("request_id", "method", "path", "status", "ms", "client")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in REQUEST_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        request_id = getattr(record, "request_id", None)
        if request_id:
            return f"{base}  [req {request_id}]"
        return base


def configure_logging() -> None:
    level = os.environ.get("ATLAS_LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler()
    if os.environ.get("ATLAS_LOG_JSON", "").lower() in {"1", "true", "yes"}:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(TextFormatter("%(levelname)s  %(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
