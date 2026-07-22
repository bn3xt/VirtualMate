from __future__ import annotations

from pathlib import Path
import shutil

from fastapi.testclient import TestClient

from virtual_mate.app import create_app


def test_app_exposes_get_and_websocket_but_no_post_routes(tmp_path: Path) -> None:
    app = create_app(runtime_root=tmp_path)
    route_methods = {
        (route.path, method)
        for route in app.routes
        for method in (getattr(route, "methods", None) or set())
    }

    assert ("/", "GET") in route_methods
    assert ("/api/bootstrap", "GET") in route_methods
    assert all(method != "POST" for _path, method in route_methods)


def test_built_frontend_is_served_with_get_requests(tmp_path: Path) -> None:
    product_root = Path(__file__).resolve().parents[2]
    shutil.copytree(product_root / "frontend" / "dist", tmp_path / "web")
    app = create_app(runtime_root=tmp_path)

    with TestClient(app) as client:
        index = client.get("/")
        script = client.get("/assets/app.js")
        styles = client.get("/assets/app.css")

    assert index.status_code == 200
    assert '<div id="root"></div>' in index.text
    assert script.status_code == 200
    assert "WebSocket" in script.text
    assert styles.status_code == 200
    assert ".sidebar" in styles.text


def test_bootstrap_is_public_and_secret_safe(tmp_path: Path) -> None:
    app = create_app(runtime_root=tmp_path)
    with TestClient(app) as client:
        response = client.get("/api/bootstrap")

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile"]["id"] == "personal_legacy_v1"
    assert payload["knowledge"] == {"ready": False, "documents": 0, "chunks": 0}
    assert payload["avatar"] == {"configured": False, "revision": 0}
    assert payload["paths"]["knowledge"].endswith("workspace\\knowledge") or payload["paths"]["knowledge"].endswith("workspace/knowledge")
    assert "api_key" not in response.text


def test_avatar_refresh_uses_fixed_workspace_file(tmp_path: Path) -> None:
    app = create_app(runtime_root=tmp_path)
    avatar = tmp_path / "workspace" / "avatar.png"
    with TestClient(app) as client:
        default_avatar = client.get("/api/avatar")
        avatar.write_bytes(b"not-a-real-png-for-transport-test")
        with client.websocket_connect("/ws") as socket:
            socket.send_json({"request_id": "avatar", "action": "refresh_avatar", "payload": {}})
            refreshed = socket.receive_json()
        configured_avatar = client.get("/api/avatar")

    assert default_avatar.status_code == 200
    assert b"VirtualMate" in default_avatar.content
    assert configured_avatar.status_code == 200
    assert configured_avatar.content == b"not-a-real-png-for-transport-test"
    assert refreshed["ok"] is True
    assert refreshed["payload"]["avatar"] == {"configured": True, "revision": 1}


def test_websocket_toggles_model_traffic_logging_without_exposing_secrets(tmp_path: Path) -> None:
    app = create_app(runtime_root=tmp_path)
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as socket:
            socket.send_json(
                {
                    "request_id": "server",
                    "action": "save_model_server",
                    "payload": {
                        "server": {
                            "id": "s",
                            "alias": "Server",
                            "base_url": "https://example.test/v1",
                            "api_key": "api-secret",
                            "proxy_password": "proxy-secret",
                        }
                    },
                }
            )
            socket.receive_json()
            socket.send_json(
                {
                    "request_id": "logging",
                    "action": "set_model_traffic_logging",
                    "payload": {"enabled": True},
                }
            )
            result = socket.receive_json()

    assert result["ok"] is True
    assert result["payload"]["diagnostics"]["model_traffic_logging"] is True
    assert result["payload"]["paths"]["model_traffic_log"].endswith("model-traffic.jsonl")
    assert "api-secret" not in str(result)
    assert "proxy-secret" not in str(result)


def test_websocket_correlates_get_state_and_rejects_unknown_action(tmp_path: Path) -> None:
    app = create_app(runtime_root=tmp_path)
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as socket:
            socket.send_json({"request_id": "r1", "action": "get_state", "payload": {}})
            result = socket.receive_json()
            assert result["request_id"] == "r1"
            assert result["type"] == "result"
            assert result["ok"] is True

            socket.send_json({"request_id": "r2", "action": "does_not_exist", "payload": {}})
            error = socket.receive_json()
            assert error["request_id"] == "r2"
            assert error["type"] == "result"
            assert error["ok"] is False
            assert "Unsupported action" in error["error"]


def test_websocket_saves_multiple_servers_and_assigns_independent_roles(tmp_path: Path) -> None:
    app = create_app(runtime_root=tmp_path)
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as socket:
            for request_id, server in (
                ("s1", {"id": "or", "alias": "OpenRouter", "base_url": "https://openrouter.ai/api/v1", "api_key": "secret"}),
                ("s2", {"id": "emb", "alias": "Embeddings", "base_url": "http://127.0.0.1:8110/v1"}),
            ):
                socket.send_json({"request_id": request_id, "action": "save_model_server", "payload": {"server": server}})
                saved = socket.receive_json()
                assert saved["ok"] is True
                assert "secret" not in str(saved)

            socket.send_json(
                {
                    "request_id": "roles",
                    "action": "assign_roles",
                    "payload": {
                        "chat": {"server_id": "or", "model_id": "mistralai/ministral-14b-2512"},
                        "embeddings": {"server_id": "emb", "model_id": "Alibaba-NLP/gte-multilingual-base"},
                    },
                }
            )
            assigned = socket.receive_json()

    assert assigned["ok"] is True
    assert assigned["payload"]["roles"]["chat"]["server_id"] == "or"
    assert assigned["payload"]["roles"]["embeddings"]["server_id"] == "emb"


def test_editing_server_without_api_key_preserves_existing_secret(tmp_path: Path) -> None:
    app = create_app(runtime_root=tmp_path)
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as socket:
            socket.send_json(
                {
                    "request_id": "create",
                    "action": "save_model_server",
                    "payload": {"server": {"id": "s", "alias": "Old", "base_url": "https://example.test/v1", "api_key": "kept-secret"}},
                }
            )
            socket.receive_json()
            socket.send_json(
                {
                    "request_id": "edit",
                    "action": "save_model_server",
                    "payload": {"server": {"id": "s", "alias": "New", "base_url": "https://example.test/v1"}},
                }
            )
            edited = socket.receive_json()

    assert edited["ok"] is True
    assert edited["payload"]["model_servers"][0]["alias"] == "New"
    assert edited["payload"]["model_servers"][0]["has_api_key"] is True
    assert "kept-secret" not in str(edited)


def test_websocket_discovers_models_and_probes_embeddings(tmp_path: Path) -> None:
    calls: list[tuple[str, str | None]] = []

    class FakeClient:
        def discover_models(self) -> list[str]:
            calls.append(("discover", None))
            return ["model-a", "embedding-a"]

        def probe_embeddings(self, model_id: str) -> int:
            calls.append(("probe", model_id))
            return 768

    app = create_app(runtime_root=tmp_path, model_client_factory=lambda _server, _paths: FakeClient())
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as socket:
            socket.send_json(
                {
                    "request_id": "save",
                    "action": "save_model_server",
                    "payload": {"server": {"id": "s", "alias": "Server", "base_url": "https://example.test/v1"}},
                }
            )
            assert socket.receive_json()["ok"] is True
            socket.send_json({"request_id": "models", "action": "discover_models", "payload": {"server_id": "s"}})
            models = socket.receive_json()
            socket.send_json(
                {
                    "request_id": "probe",
                    "action": "probe_embeddings",
                    "payload": {"server_id": "s", "model_id": "embedding-a"},
                }
            )
            probe = socket.receive_json()

    assert models["payload"] == {"server_id": "s", "models": ["model-a", "embedding-a"]}
    assert probe["payload"] == {"server_id": "s", "model_id": "embedding-a", "dimension": 768}
    assert calls == [("discover", None), ("probe", "embedding-a")]


def test_delete_server_clears_role_references(tmp_path: Path) -> None:
    app = create_app(runtime_root=tmp_path)
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as socket:
            socket.send_json(
                {
                    "request_id": "save",
                    "action": "save_model_server",
                    "payload": {"server": {"id": "s", "alias": "Server", "base_url": "https://example.test/v1"}},
                }
            )
            socket.receive_json()
            socket.send_json(
                {
                    "request_id": "roles",
                    "action": "assign_roles",
                    "payload": {"chat": {"server_id": "s", "model_id": "model-a"}},
                }
            )
            socket.receive_json()
            socket.send_json({"request_id": "delete", "action": "delete_model_server", "payload": {"server_id": "s"}})
            deleted = socket.receive_json()

    assert deleted["ok"] is True
    assert deleted["payload"]["model_servers"] == []
    assert deleted["payload"]["roles"] == {"chat": None, "embeddings": None}


def test_persona_status_and_reload_are_available_over_websocket(tmp_path: Path) -> None:
    app = create_app(runtime_root=tmp_path)
    persona = tmp_path / "workspace" / "persona.md"
    persona.write_text("# Mateo\n\nVamos por partes.", encoding="utf-8")

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as socket:
            socket.send_json({"request_id": "persona", "action": "reload_persona", "payload": {}})
            result = socket.receive_json()

    assert result["ok"] is True
    assert result["payload"]["persona"]["loaded"] is True
    assert result["payload"]["persona"]["estimated_tokens"] > 0
    assert "Vamos por partes" not in str(result)


def test_process_knowledge_emits_correlated_progress_and_terminal_result(tmp_path: Path) -> None:
    class FakeClient:
        def generate_embeddings(self, texts: list[str], *, model_id: str, batch_size: int = 64) -> list[list[float]]:
            assert model_id == "embedding-a"
            return [[float(len(text)), 0.1, 0.2] for text in texts]

    app = create_app(runtime_root=tmp_path, model_client_factory=lambda _server, _paths: FakeClient())
    (tmp_path / "workspace" / "knowledge" / "source.md").write_text(
        "# Source\n\nRelay Envelope v3.", encoding="utf-8"
    )
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as socket:
            socket.send_json(
                {
                    "request_id": "save",
                    "action": "save_model_server",
                    "payload": {"server": {"id": "emb", "alias": "Embeddings", "base_url": "http://127.0.0.1:8110/v1"}},
                }
            )
            socket.receive_json()
            socket.send_json(
                {
                    "request_id": "roles",
                    "action": "assign_roles",
                    "payload": {"embeddings": {"server_id": "emb", "model_id": "embedding-a"}},
                }
            )
            socket.receive_json()
            socket.send_json({"request_id": "process", "action": "process_knowledge", "payload": {}})
            messages: list[dict] = []
            while True:
                message = socket.receive_json()
                messages.append(message)
                if message["type"] == "result":
                    break

    assert all(message["request_id"] == "process" for message in messages)
    assert any(message["type"] == "progress" and message["payload"]["phase"] == "chunked" for message in messages)
    vectorization = [message["payload"] for message in messages if message["type"] == "progress" and message["payload"]["phase"] == "vectorizing"]
    assert vectorization[-1]["vectorization_current"] == vectorization[-1]["vectorization_total"] == 1
    terminal = messages[-1]
    assert terminal["ok"] is True
    assert terminal["payload"]["documents_processed"] == 1
    assert terminal["payload"]["chunks_generated"] == 1


def test_websocket_chat_runs_current_rag_and_returns_cited_evidence(tmp_path: Path) -> None:
    class FakeClient:
        def generate_embeddings(self, texts: list[str], *, model_id: str, batch_size: int = 64) -> list[list[float]]:
            vectors: list[list[float]] = []
            for text in texts:
                lowered = text.lower()
                vectors.append([1.0 if "relay" in lowered else 0.0, 1.0 if "password" in lowered else 0.0, 0.1])
            return vectors

        def chat_completion(self, messages: list[dict[str, str]], *, model_id: str, max_tokens: int) -> str:
            assert model_id == "chat-a"
            assert max_tokens == 2_500
            question = messages[-1]["content"].lower()
            if "password" in question:
                return "The password is swordfish."
            assert any(message["content"].startswith("CURRENT EVIDENCE") for message in messages)
            return "Relay Envelope v3 connects Northstar and Meridian [E1]."

    app = create_app(runtime_root=tmp_path, model_client_factory=lambda _server, _paths: FakeClient())
    (tmp_path / "workspace" / "persona.md").write_text("# Mateo\n\nVamos por partes.", encoding="utf-8")
    (tmp_path / "workspace" / "knowledge" / "architecture.md").write_text(
        "# Architecture\n\nRelay Envelope v3 connects Northstar and Meridian.", encoding="utf-8"
    )
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as socket:
            for request_id, server in (
                ("s1", {"id": "chat", "alias": "Chat", "base_url": "https://chat.test/v1"}),
                ("s2", {"id": "emb", "alias": "Embeddings", "base_url": "http://127.0.0.1:8110/v1"}),
            ):
                socket.send_json({"request_id": request_id, "action": "save_model_server", "payload": {"server": server}})
                socket.receive_json()
            socket.send_json(
                {
                    "request_id": "roles",
                    "action": "assign_roles",
                    "payload": {
                        "chat": {"server_id": "chat", "model_id": "chat-a"},
                        "embeddings": {"server_id": "emb", "model_id": "embedding-a"},
                    },
                }
            )
            socket.receive_json()
            socket.send_json({"request_id": "persona", "action": "reload_persona", "payload": {}})
            socket.receive_json()
            socket.send_json({"request_id": "process", "action": "process_knowledge", "payload": {}})
            while socket.receive_json()["type"] != "result":
                pass

            socket.send_json(
                {"request_id": "chat-1", "action": "chat", "payload": {"message": "What does the relay connect?"}}
            )
            answer_messages: list[dict] = []
            while True:
                event = socket.receive_json()
                answer_messages.append(event)
                if event["type"] == "result":
                    answer = event
                    break
            socket.send_json(
                {"request_id": "chat-2", "action": "chat", "payload": {"message": "What is the production password?"}}
            )
            while True:
                event = socket.receive_json()
                if event["type"] == "result":
                    missing = event
                    break
            socket.send_json({"request_id": "clear", "action": "clear_chat", "payload": {}})
            cleared = socket.receive_json()

    assert answer["ok"] is True
    assert [event["payload"]["phase"] for event in answer_messages if event["type"] == "progress"] == [
        "retrieving",
        "evidence_ready",
        "generating",
    ]
    assert "Northstar and Meridian [E1]" in answer["payload"]["answer"]
    assert answer["payload"]["evidence"][0]["relative_path"] == "architecture.md"
    assert missing["ok"] is True
    assert "insufficient" in missing["payload"]["answer"].lower()
    assert missing["payload"]["evidence"] == []
    assert cleared["payload"]["chat_message_count"] == 0

