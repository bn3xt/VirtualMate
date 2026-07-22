from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from virtual_mate.config import ModelServerConfig
from virtual_mate.model_servers import (
    ModelServerClient,
    ModelServerError,
    parse_model_ids,
    resolve_proxy,
    resolve_tls_verify,
)
from virtual_mate.paths import resolve_paths


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"data": [{"id": "m1"}, {"id": "m2"}]}, ["m1", "m2"]),
        ([{"id": "m1"}, {"id": "m2"}], ["m1", "m2"]),
        ({"id": "single"}, ["single"]),
    ],
)
def test_parse_model_ids_accepts_openai_compatible_shapes(payload: object, expected: list[str]) -> None:
    assert parse_model_ids(payload) == expected


def test_parse_model_ids_rejects_unexpected_or_empty_payloads() -> None:
    with pytest.raises(ModelServerError):
        parse_model_ids({"data": []})
    with pytest.raises(ModelServerError):
        parse_model_ids({"models": ["wrong"]})


def test_tls_verify_uses_fixed_corporate_ca(tmp_path: Path) -> None:
    paths = resolve_paths(tmp_path)
    paths.workspace_dir.mkdir(parents=True)
    paths.corporate_ca_path.write_text("PEM", encoding="utf-8")
    server = ModelServerConfig(
        id="s",
        alias="Server",
        base_url="https://example.test/v1",
        verify_ssl=True,
        use_corporate_ca=True,
    )

    assert resolve_tls_verify(server, paths) == str(paths.corporate_ca_path.resolve())


def test_tls_verify_fails_when_fixed_ca_is_missing(tmp_path: Path) -> None:
    server = ModelServerConfig(
        id="s",
        alias="Server",
        base_url="https://example.test/v1",
        use_corporate_ca=True,
    )

    with pytest.raises(ModelServerError, match="corporate-ca.pem"):
        resolve_tls_verify(server, resolve_paths(tmp_path))


def test_proxy_resolution_matches_substrate_https_first_and_no_proxy() -> None:
    server = ModelServerConfig(
        id="s",
        alias="Server",
        base_url="https://models.company.test/v1",
        proxy_enabled=True,
        http_proxy="http://http-proxy.test:8080",
        https_proxy="http://https-proxy.test:8080",
        proxy_username="domain-user",
        proxy_password="proxy-secret",
    )
    assert resolve_proxy(server) == "http://domain-user:proxy-secret@https-proxy.test:8080"

    bypassed = server.model_copy(update={"no_proxy": ".company.test"})
    assert resolve_proxy(bypassed) is None


def test_model_discovery_uses_get_and_bearer_without_leaking_key(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["authorization"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"data": [{"id": "chat-model"}]})

    server = ModelServerConfig(
        id="s",
        alias="Server",
        base_url="https://example.test/v1",
        api_key="secret-token",
    )
    client = ModelServerClient(server=server, paths=resolve_paths(tmp_path), transport=httpx.MockTransport(handler))

    assert client.discover_models() == ["chat-model"]
    assert captured == {"method": "GET", "path": "/v1/models", "authorization": "Bearer secret-token"}


def test_model_discovery_redacts_provider_error_body(tmp_path: Path) -> None:
    secret = "secret-token"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text=f"bad credential {secret}")

    server = ModelServerConfig(
        id="s", alias="Server", base_url="https://example.test/v1", api_key=secret
    )
    client = ModelServerClient(server=server, paths=resolve_paths(tmp_path), transport=httpx.MockTransport(handler))

    with pytest.raises(ModelServerError) as raised:
        client.discover_models()
    assert secret not in str(raised.value)


def test_embedding_probe_returns_dimension(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/embeddings"
        payload = json.loads(request.content)
        assert payload["model"] == "embedding-model"
        return httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2, 0.3]}]})

    server = ModelServerConfig(id="s", alias="Server", base_url="https://example.test/v1")
    client = ModelServerClient(server=server, paths=resolve_paths(tmp_path), transport=httpx.MockTransport(handler))

    assert client.probe_embeddings("embedding-model") == 3


def test_generate_embeddings_preserves_input_order_and_batches(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        inputs = payload["input"]
        calls.append(inputs)
        return httpx.Response(
            200,
            json={"data": [{"index": index, "embedding": [float(len(text)), float(index)]} for index, text in enumerate(inputs)]},
        )

    server = ModelServerConfig(id="s", alias="Server", base_url="https://example.test/v1")
    client = ModelServerClient(server=server, paths=resolve_paths(tmp_path), transport=httpx.MockTransport(handler))

    vectors = client.generate_embeddings(["a", "bb", "ccc"], model_id="embedding-model", batch_size=2)

    assert calls == [["a", "bb"], ["ccc"]]
    assert vectors == [[1.0, 0.0], [2.0, 1.0], [3.0, 0.0]]


def test_embeddings_does_not_retry_an_oversized_batch(tmp_path: Path) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(413, text="Maximum batch size is 32")

    client = ModelServerClient(
        server=ModelServerConfig(id="s", alias="Server", base_url="https://example.test/v1"),
        paths=resolve_paths(tmp_path),
        transport=httpx.MockTransport(handler),
    )
    client.set_runtime_tuning(
        timeout_seconds=60,
        embedding_retry_attempts=3,
        embedding_retry_delay_seconds=0,
        embedding_inter_request_delay_ms=0,
    )

    with pytest.raises(ModelServerError, match="HTTP 413"):
        client.generate_embeddings(["one", "two"], model_id="embedding-model", batch_size=2)
    assert calls == 1


def test_embeddings_retries_transient_provider_failures(tmp_path: Path) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(500, text="temporary provider failure")
        return httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2]}]})

    client = ModelServerClient(
        server=ModelServerConfig(id="s", alias="Server", base_url="https://example.test/v1"),
        paths=resolve_paths(tmp_path),
        transport=httpx.MockTransport(handler),
    )
    client.set_runtime_tuning(
        timeout_seconds=60,
        embedding_retry_attempts=1,
        embedding_retry_delay_seconds=0,
        embedding_inter_request_delay_ms=0,
    )

    assert client.generate_embeddings(["one"], model_id="embedding-model", batch_size=1) == [[0.1, 0.2]]
    assert calls == 2


def test_chat_completion_uses_openai_payload_and_extracts_text(tmp_path: Path) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "Grounded answer [E1]."}}]})

    server = ModelServerConfig(id="s", alias="Server", base_url="https://example.test/v1")
    client = ModelServerClient(server=server, paths=resolve_paths(tmp_path), transport=httpx.MockTransport(handler))

    text = client.chat_completion(
        [{"role": "user", "content": "Question"}], model_id="chat-model", max_tokens=2_500
    )

    assert text == "Grounded answer [E1]."
    assert captured == {
        "model": "chat-model",
        "messages": [{"role": "user", "content": "Question"}],
        "max_tokens": 2_500,
    }


def test_chat_completion_supports_text_content_parts(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": [{"type": "text", "text": "Part one. "}, {"text": "Part two."}]}}]},
        )

    server = ModelServerConfig(id="s", alias="Server", base_url="https://example.test/v1")
    client = ModelServerClient(server=server, paths=resolve_paths(tmp_path), transport=httpx.MockTransport(handler))

    assert client.chat_completion([], model_id="chat-model", max_tokens=100) == "Part one. Part two."


def test_model_traffic_log_is_opt_in_and_redacts_credentials(tmp_path: Path) -> None:
    server = ModelServerConfig(
        id="s",
        alias="Server",
        base_url="https://example.test/v1",
        api_key="api-secret",
        proxy_password="proxy-secret",
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="provider diagnostic detail")

    paths = resolve_paths(tmp_path)
    client = ModelServerClient(server=server, paths=paths, transport=httpx.MockTransport(handler))
    client.set_runtime_tuning(
        timeout_seconds=60,
        embedding_retry_attempts=0,
        embedding_retry_delay_seconds=0,
        embedding_inter_request_delay_ms=0,
    )
    with pytest.raises(ModelServerError, match="HTTP 500"):
        client.probe_embeddings("embedding-model")
    assert not paths.model_traffic_log_path.exists()

    client.set_model_traffic_logging(True)
    with pytest.raises(ModelServerError, match="HTTP 500"):
        client.probe_embeddings("embedding-model")

    logged = paths.model_traffic_log_path.read_text(encoding="utf-8")
    assert "provider diagnostic detail" in logged
    assert "embedding-model" in logged
    assert "api-secret" not in logged
    assert "proxy-secret" not in logged

