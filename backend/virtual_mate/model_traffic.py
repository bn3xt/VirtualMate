from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


_SECRET_KEYS = {"api_key", "apikey", "authorization", "proxy-authorization", "token", "password"}


def _redact(value: Any, *, key: str | None = None) -> Any:
    if key:
        normalized = key.lower().replace("-", "_")
        if normalized in _SECRET_KEYS or normalized.endswith("_password"):
            return "<redacted>"
    if isinstance(value, dict):
        return {str(item_key): _redact(item_value, key=str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


class ModelTrafficLogger:
    """Optional JSONL trace of model HTTP traffic for local troubleshooting."""

    def __init__(self, path: Path, *, enabled: bool) -> None:
        self.path = Path(path)
        self.enabled = bool(enabled)

    def exchange(self, *, server_id: str, request: httpx.Request, response: httpx.Response) -> None:
        self._write(
            {
                "event": "model_http",
                "server_id": server_id,
                "request": {
                    "method": request.method,
                    "url": str(request.url),
                    "headers": _redact(dict(request.headers)),
                    "body": self._body(request.content),
                },
                "response": {
                    "status_code": response.status_code,
                    "headers": _redact(dict(response.headers)),
                    "body": response.text,
                },
            }
        )

    def failure(self, *, server_id: str, method: str, url: str, payload: object | None, error: Exception) -> None:
        self._write(
            {
                "event": "model_http_failure",
                "server_id": server_id,
                "request": {"method": method, "url": url, "body": _redact(payload)},
                "error": {"type": error.__class__.__name__, "message": str(error)},
            }
        )

    def _write(self, payload: dict[str, Any]) -> None:
        if not self.enabled:
            return
        record = {"timestamp": datetime.now(timezone.utc).isoformat(), **payload}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except OSError:
            # Diagnostics must never interfere with an actual model call.
            return

    @staticmethod
    def _body(content: bytes) -> Any:
        if not content:
            return None
        try:
            return _redact(json.loads(content.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return content.decode("utf-8", errors="replace")


__all__ = ["ModelTrafficLogger"]
