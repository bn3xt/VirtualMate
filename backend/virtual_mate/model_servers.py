from __future__ import annotations

from pathlib import Path
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from .config import ModelServerConfig
from .model_traffic import ModelTrafficLogger
from .paths import RuntimePaths


class ModelServerError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def resolve_tls_verify(server: ModelServerConfig, paths: RuntimePaths) -> bool | str:
    if server.use_corporate_ca:
        if not paths.corporate_ca_path.is_file():
            raise ModelServerError(
                f"Corporate CA is enabled but {paths.corporate_ca_path.name} is missing from the fixed workspace path"
            )
        return str(paths.corporate_ca_path.resolve())
    return bool(server.verify_ssl)


def _host_matches_no_proxy(host: str, no_proxy: str | None) -> bool:
    if not no_proxy:
        return False
    candidate = host.lower()
    for raw in no_proxy.split(","):
        token = raw.strip().lower()
        if token == "*" or candidate == token:
            return True
        if token.startswith(".") and candidate.endswith(token):
            return True
    return False


def _proxy_with_credentials(proxy_url: str, username: str | None, password: str | None) -> str:
    if not proxy_url or not username or not password:
        return proxy_url
    parsed = urlparse(proxy_url)
    if parsed.username or parsed.password:
        return proxy_url
    host = parsed.hostname or ""
    netloc = f"{username}:{password}@{host}"
    if parsed.port:
        netloc += f":{parsed.port}"
    return parsed._replace(netloc=netloc).geturl()


def resolve_proxy(server: ModelServerConfig) -> str | None:
    """Mirror Substrate's proxy/no-proxy selection for OpenAI-compatible calls."""
    if not server.proxy_enabled:
        return None
    host = urlparse(server.base_url).hostname or ""
    if _host_matches_no_proxy(host, server.no_proxy):
        return None
    proxy_url = server.https_proxy or server.http_proxy
    return _proxy_with_credentials(str(proxy_url or ""), server.proxy_username, server.proxy_password) or None


def parse_model_ids(payload: Any) -> list[str]:
    candidates: Any
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        candidates = payload["data"]
    elif isinstance(payload, list):
        candidates = payload
    elif isinstance(payload, dict) and isinstance(payload.get("id"), str):
        candidates = [payload]
    else:
        raise ModelServerError("Model server returned an unexpected /models response")
    model_ids = [str(item.get("id") or "").strip() for item in candidates if isinstance(item, dict)]
    model_ids = list(dict.fromkeys(item for item in model_ids if item))
    if not model_ids:
        raise ModelServerError("Model server returned no model identifiers")
    return model_ids


class ModelServerClient:
    """Reduced standalone adaptation of Substrate's OpenAI-compatible HTTP client."""

    def __init__(
        self,
        *,
        server: ModelServerConfig,
        paths: RuntimePaths,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.server = server
        self.paths = paths
        self.timeout = timeout
        self.transport = transport
        self.model_traffic_logging = False
        self.embedding_retry_attempts = 2
        self.embedding_retry_delay_seconds = 2.0
        self.embedding_inter_request_delay_ms = 0

    def set_model_traffic_logging(self, enabled: bool) -> None:
        self.model_traffic_logging = bool(enabled)

    def set_runtime_tuning(
        self,
        *,
        timeout_seconds: float,
        embedding_retry_attempts: int,
        embedding_retry_delay_seconds: float,
        embedding_inter_request_delay_ms: int,
    ) -> None:
        self.timeout = float(timeout_seconds)
        self.embedding_retry_attempts = max(0, int(embedding_retry_attempts))
        self.embedding_retry_delay_seconds = max(0.0, float(embedding_retry_delay_seconds))
        self.embedding_inter_request_delay_ms = max(0, int(embedding_inter_request_delay_ms))

    def _client(self) -> httpx.Client:
        headers = {"Content-Type": "application/json"}
        if self.server.api_key:
            headers["Authorization"] = f"Bearer {self.server.api_key}"
        kwargs: dict[str, Any] = {
            "base_url": self.server.base_url.rstrip("/") + "/",
            "headers": headers,
            "verify": resolve_tls_verify(self.server, self.paths),
            "follow_redirects": self.server.follow_redirects,
            "timeout": self.timeout,
        }
        proxy = resolve_proxy(self.server)
        if proxy:
            kwargs["proxy"] = proxy
        if self.transport is not None:
            kwargs["transport"] = self.transport
        return httpx.Client(**kwargs)

    def _request(
        self,
        client: httpx.Client,
        method: str,
        endpoint: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> httpx.Response:
        trace = ModelTrafficLogger(self.paths.model_traffic_log_path, enabled=self.model_traffic_logging)
        try:
            response = client.request(method, endpoint, json=payload)
        except Exception as exc:
            trace.failure(
                server_id=self.server.id,
                method=method,
                url=str(client.base_url.join(endpoint)),
                payload=payload,
                error=exc,
            )
            raise
        trace.exchange(server_id=self.server.id, request=response.request, response=response)
        return response

    def discover_models(self) -> list[str]:
        try:
            with self._client() as client:
                response = self._request(client, "GET", "models")
        except ModelServerError:
            raise
        except Exception as exc:
            raise ModelServerError(f"Could not connect to model server: {exc.__class__.__name__}") from exc
        if response.status_code != 200:
            raise ModelServerError(f"Model server /models returned HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ModelServerError("Model server /models returned invalid JSON") from exc
        return parse_model_ids(payload)

    def probe_embeddings(self, model_id: str) -> int:
        vectors = self.generate_embeddings(
            ["VirtualMate embeddings probe"], model_id=model_id, batch_size=1
        )
        return len(vectors[0])

    def generate_embeddings(
        self,
        texts: list[str],
        *,
        model_id: str,
        batch_size: int = 64,
    ) -> list[list[float]]:
        if not texts:
            return []
        size = max(1, int(batch_size))
        vectors: list[list[float]] = []
        try:
            with self._client() as client:
                for batch_index, start in enumerate(range(0, len(texts), size)):
                    batch = texts[start : start + size]
                    if batch_index and self.embedding_inter_request_delay_ms:
                        time.sleep(self.embedding_inter_request_delay_ms / 1000.0)
                    payload = {"model": model_id, "input": batch}
                    for attempt in range(self.embedding_retry_attempts + 1):
                        try:
                            response = self._request(client, "POST", "embeddings", payload=payload)
                            batch_vectors = self._parse_embedding_response(response, expected=len(batch))
                        except ModelServerError as exc:
                            # Retrying an oversized request cannot succeed; lower the configured batch size instead.
                            if exc.status_code == 413 or attempt >= self.embedding_retry_attempts:
                                raise
                            time.sleep(self.embedding_retry_delay_seconds)
                            continue
                        except httpx.HTTPError:
                            if attempt >= self.embedding_retry_attempts:
                                raise
                            time.sleep(self.embedding_retry_delay_seconds)
                            continue
                        vectors.extend(batch_vectors)
                        break
        except ModelServerError:
            raise
        except Exception as exc:
            raise ModelServerError(f"Could not connect to embeddings server: {exc.__class__.__name__}") from exc

        if len(vectors) != len(texts):
            raise ModelServerError("Embeddings endpoint returned an unexpected vector count")
        dimensions = {len(vector) for vector in vectors}
        if len(dimensions) != 1 or 0 in dimensions:
            raise ModelServerError("Embeddings endpoint returned inconsistent vector dimensions")
        return vectors

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        *,
        model_id: str,
        max_tokens: int,
    ) -> str:
        payload = {
            "model": model_id,
            "messages": messages,
            "max_tokens": int(max_tokens),
        }
        try:
            with self._client() as client:
                response = self._request(client, "POST", "chat/completions", payload=payload)
        except ModelServerError:
            raise
        except Exception as exc:
            raise ModelServerError(f"Could not connect to chat server: {exc.__class__.__name__}") from exc
        if response.status_code != 200:
            raise ModelServerError(f"Chat endpoint returned HTTP {response.status_code}", status_code=response.status_code)
        try:
            body = response.json()
            choices = body.get("choices") if isinstance(body, dict) else None
            message = choices[0].get("message") if isinstance(choices, list) and choices and isinstance(choices[0], dict) else None
            content = message.get("content") if isinstance(message, dict) else None
        except (ValueError, TypeError, IndexError) as exc:
            raise ModelServerError("Chat endpoint returned an invalid response") from exc
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            parts = [str(part.get("text") or "") for part in content if isinstance(part, dict)]
            text = "".join(parts).strip()
            if text:
                return text
        raise ModelServerError("Chat endpoint returned an empty answer")

    @staticmethod
    def _parse_embedding_response(response: httpx.Response, *, expected: int) -> list[list[float]]:
        if response.status_code != 200:
            raise ModelServerError(
                f"Embeddings endpoint returned HTTP {response.status_code}", status_code=response.status_code
            )
        try:
            body = response.json()
            items = body.get("data") if isinstance(body, dict) else None
        except ValueError as exc:
            raise ModelServerError("Embeddings endpoint returned an invalid response") from exc
        if not isinstance(items, list) or len(items) != expected:
            raise ModelServerError("Embeddings endpoint returned an unexpected vector count")
        ordered = sorted(
            (item for item in items if isinstance(item, dict)),
            key=lambda item: int(item.get("index", 0)),
        )
        vectors: list[list[float]] = []
        for item in ordered:
            raw = item.get("embedding")
            if not isinstance(raw, list) or not raw:
                raise ModelServerError("Embeddings endpoint returned an empty vector")
            try:
                vectors.append([float(value) for value in raw])
            except (TypeError, ValueError) as exc:
                raise ModelServerError("Embeddings endpoint returned a non-numeric vector") from exc
        return vectors


__all__ = ["ModelServerClient", "ModelServerError", "parse_model_ids", "resolve_proxy", "resolve_tls_verify"]

