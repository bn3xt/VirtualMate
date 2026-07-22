from __future__ import annotations

import asyncio
from dataclasses import asdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .chat import ChatService
from .config import AppConfig, ConfigRepository, ModelRef, ModelServerConfig, RoleAssignments
from .ingestion.processor import KnowledgeProcessor
from .model_servers import ModelServerClient
from .paths import RuntimePaths, bootstrap_workspace, resolve_paths
from .persona import PersonaService
from .profile import PERSONAL_LEGACY_PROFILE
from .retrieval import RetrievalEngine
from .storage import ChromaStore, CorpusStore


_INDEX_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>VirtualMate</title></head>
<body><main><h1>VirtualMate</h1><p>Standalone runtime is ready.</p></main></body></html>"""

_DEFAULT_AVATAR_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" role="img" aria-label="VirtualMate"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#10a37f"/><stop offset="1" stop-color="#3b82f6"/></linearGradient></defs><rect width="128" height="128" rx="32" fill="url(#g)"/><path d="M32 40h16l16 41 16-41h16L72 97H56z" fill="#fff"/></svg>"""


@dataclass(slots=True)
class ApplicationState:
    paths: RuntimePaths
    repository: ConfigRepository
    config: AppConfig
    persona: PersonaService
    model_client_factory: Callable[[ModelServerConfig, RuntimePaths], Any]
    chat_history: list[dict[str, str]] = field(default_factory=list)
    avatar_revision: int = 0

    def public_payload(self) -> dict[str, Any]:
        public_config = self.config.public_dict()
        persona = self.persona.active
        corpus = CorpusStore(self.paths.database_path)
        document_count = corpus.document_count()
        chunk_count = corpus.chunk_count()
        return {
            "model_servers": public_config["model_servers"],
            "roles": public_config["roles"],
            "profile": PERSONAL_LEGACY_PROFILE.public_dict(),
            "persona": {
                "loaded": persona is not None,
                "estimated_tokens": persona.estimated_tokens if persona else 0,
                "over_budget": persona.over_budget if persona else False,
            },
            "avatar": {
                "configured": self.paths.avatar_path.is_file(),
                "revision": self.avatar_revision,
            },
            "chat_message_count": len(self.chat_history),
            "knowledge": {
                "ready": document_count > 0 and chunk_count > 0,
                "documents": document_count,
                "chunks": chunk_count,
            },
            "paths": {
                "workspace": str(self.paths.workspace_dir),
                "knowledge": str(self.paths.knowledge_dir),
                "persona": str(self.paths.persona_path),
                "avatar": str(self.paths.avatar_path),
                "corporate_ca": str(self.paths.corporate_ca_path),
                "model_traffic_log": str(self.paths.model_traffic_log_path),
            },
            "diagnostics": {
                "model_traffic_logging": self.config.model_traffic_logging,
            },
        }

    def save_model_server(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_server = payload.get("server")
        if not isinstance(raw_server, dict):
            raise ValueError("server must be an object")
        normalized = dict(raw_server)
        existing = next(
            (item for item in self.config.model_servers if item.id == str(normalized.get("id") or "").strip()),
            None,
        )
        if "api_key" not in normalized and existing is not None:
            normalized["api_key"] = existing.api_key
        if "proxy_password" not in normalized and existing is not None:
            normalized["proxy_password"] = existing.proxy_password
        server = ModelServerConfig.model_validate(normalized)
        servers = [item for item in self.config.model_servers if item.id != server.id]
        servers.append(server)
        candidate = self.config.model_copy(update={"model_servers": servers})
        candidate.validate_role_references()
        self.repository.save(candidate)
        self.config = candidate
        return self.public_payload()

    def assign_roles(self, payload: dict[str, Any]) -> dict[str, Any]:
        roles = RoleAssignments(
            chat=ModelRef.model_validate(payload["chat"]) if payload.get("chat") else None,
            embeddings=ModelRef.model_validate(payload["embeddings"]) if payload.get("embeddings") else None,
        )
        candidate = self.config.model_copy(update={"roles": roles})
        candidate.validate_role_references()
        self.repository.save(candidate)
        self.config = candidate
        return self.public_payload()

    def delete_model_server(self, payload: dict[str, Any]) -> dict[str, Any]:
        server_id = str(payload.get("server_id") or "").strip()
        if not server_id:
            raise ValueError("server_id is required")
        servers = [item for item in self.config.model_servers if item.id != server_id]
        if len(servers) == len(self.config.model_servers):
            raise ValueError(f"Model server not found: {server_id}")
        roles = self.config.roles.model_copy(
            update={
                "chat": None if self.config.roles.chat and self.config.roles.chat.server_id == server_id else self.config.roles.chat,
                "embeddings": None
                if self.config.roles.embeddings and self.config.roles.embeddings.server_id == server_id
                else self.config.roles.embeddings,
            }
        )
        candidate = self.config.model_copy(update={"model_servers": servers, "roles": roles})
        self.repository.save(candidate)
        self.config = candidate
        return self.public_payload()

    def _server(self, server_id: str) -> ModelServerConfig:
        server = next((item for item in self.config.model_servers if item.id == server_id and item.enabled), None)
        if server is None:
            raise ValueError(f"Model server not found or disabled: {server_id}")
        return server

    def _client(self, server: ModelServerConfig) -> Any:
        client = self.model_client_factory(server, self.paths)
        if isinstance(client, ModelServerClient):
            client.set_model_traffic_logging(self.config.model_traffic_logging)
            tuning = self.config.runtime_tuning
            client.set_runtime_tuning(
                timeout_seconds=tuning.model_request_timeout_seconds,
                embedding_retry_attempts=tuning.embedding_retry_attempts,
                embedding_retry_delay_seconds=tuning.embedding_retry_delay_seconds,
                embedding_inter_request_delay_ms=tuning.embedding_inter_request_delay_ms,
            )
        return client

    def discover_models(self, payload: dict[str, Any]) -> dict[str, Any]:
        server_id = str(payload.get("server_id") or "").strip()
        server = self._server(server_id)
        models = self._client(server).discover_models()
        return {"server_id": server_id, "models": models}

    def probe_embeddings(self, payload: dict[str, Any]) -> dict[str, Any]:
        server_id = str(payload.get("server_id") or "").strip()
        model_id = str(payload.get("model_id") or "").strip()
        if not model_id:
            raise ValueError("model_id is required")
        server = self._server(server_id)
        dimension = self._client(server).probe_embeddings(model_id)
        return {"server_id": server_id, "model_id": model_id, "dimension": dimension}

    def reload_persona(self, _payload: dict[str, Any]) -> dict[str, Any]:
        self.persona.reload()
        return self.public_payload()

    def refresh_avatar(self, _payload: dict[str, Any]) -> dict[str, Any]:
        self.avatar_revision += 1
        return self.public_payload()

    def process_knowledge(
        self,
        _payload: dict[str, Any],
        progress: Callable[[dict[str, object]], None],
    ) -> dict[str, Any]:
        ref = self.config.roles.embeddings
        if ref is None:
            raise ValueError("The embeddings role must be configured before processing knowledge")
        server = self._server(ref.server_id)
        client = self._client(server)
        embedding_batch_size = self.config.runtime_tuning.embedding_batch_size

        class ConfiguredEmbedder:
            def embed(self, texts: list[str]) -> list[list[float]]:
                return client.generate_embeddings(
                    texts,
                    model_id=ref.model_id,
                    batch_size=embedding_batch_size,
                )

        processor = KnowledgeProcessor(
            paths=self.paths,
            corpus=CorpusStore(self.paths.database_path),
            vectors=ChromaStore(self.paths.chroma_dir),
            embedder=ConfiguredEmbedder(),
            progress=progress,
            embedding_batch_size=embedding_batch_size,
        )
        return asdict(processor.process())

    def chat(
        self,
        payload: dict[str, Any],
        progress: Callable[[dict[str, object]], None] | None = None,
    ) -> dict[str, Any]:
        message = str(payload.get("message") or "").strip()
        if not message:
            raise ValueError("Chat message must not be empty")
        chat_ref = self.config.roles.chat
        embeddings_ref = self.config.roles.embeddings
        if chat_ref is None:
            raise ValueError("The chat role must be configured before asking questions")
        if embeddings_ref is None:
            raise ValueError("The embeddings role must be configured before asking questions")
        if self.persona.active is None:
            raise ValueError("The persona must be loaded before asking questions")
        chat_server = self._server(chat_ref.server_id)
        embeddings_server = self._server(embeddings_ref.server_id)
        chat_client = self._client(chat_server)
        embeddings_client = self._client(embeddings_server)
        embedding_batch_size = self.config.runtime_tuning.embedding_batch_size

        def report(phase: str, message: str, **details: object) -> None:
            if progress is not None:
                progress({"phase": phase, "message": message, **details})

        class ConfiguredEmbedder:
            def embed(self, texts: list[str]) -> list[list[float]]:
                return embeddings_client.generate_embeddings(
                    texts,
                    model_id=embeddings_ref.model_id,
                    batch_size=embedding_batch_size,
                )

        retriever = RetrievalEngine(
            corpus=CorpusStore(self.paths.database_path),
            vectors=ChromaStore(self.paths.chroma_dir),
            embedder=ConfiguredEmbedder(),
        )

        class ProgressRetriever:
            def retrieve(self, query: str):
                report("retrieving", "Searching indexed memories and computing the query embedding…")
                retrieved = retriever.retrieve(query)
                report(
                    "evidence_ready",
                    "Retrieved evidence is ready; preparing the grounded answer…",
                    evidence_count=len(retrieved.evidence),
                )
                return retrieved

        class ProgressChatClient:
            def chat_completion(
                self,
                messages: list[dict[str, str]],
                *,
                model_id: str,
                max_tokens: int,
            ) -> str:
                report("generating", "Waiting for the response model to generate an answer…", model_id=model_id)
                return chat_client.chat_completion(messages, model_id=model_id, max_tokens=max_tokens)

        result = ChatService(
            retriever=ProgressRetriever(),
            chat_client=ProgressChatClient(),
            model_id=chat_ref.model_id,
        ).answer(
            message,
            persona=self.persona.active,
            history=self.chat_history,
        )
        return result.as_dict()

    def set_model_traffic_logging(self, payload: dict[str, Any]) -> dict[str, Any]:
        enabled = payload.get("enabled")
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a boolean")
        candidate = self.config.model_copy(update={"model_traffic_logging": enabled})
        self.repository.save(candidate)
        self.config = candidate
        return self.public_payload()

    def clear_chat(self, _payload: dict[str, Any]) -> dict[str, Any]:
        self.chat_history.clear()
        return {"chat_message_count": 0}

    def safe_error(self, exc: Exception) -> str:
        message = str(exc)
        for server in self.config.model_servers:
            if server.api_key:
                message = message.replace(server.api_key, "<redacted>")
            if server.proxy_password:
                message = message.replace(server.proxy_password, "<redacted>")
        return message or exc.__class__.__name__


def _dispatch(state: ApplicationState, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    actions: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
        "get_state": lambda _payload: state.public_payload(),
        "save_model_server": state.save_model_server,
        "assign_roles": state.assign_roles,
        "delete_model_server": state.delete_model_server,
        "discover_models": state.discover_models,
        "probe_embeddings": state.probe_embeddings,
        "set_model_traffic_logging": state.set_model_traffic_logging,
        "reload_persona": state.reload_persona,
        "refresh_avatar": state.refresh_avatar,
        "chat": state.chat,
        "clear_chat": state.clear_chat,
    }
    handler = actions.get(action)
    if handler is None:
        raise ValueError(f"Unsupported action: {action}")
    return handler(payload)


def create_app(
    *,
    runtime_root: str | Path | None = None,
    model_client_factory: Callable[[ModelServerConfig, RuntimePaths], Any] | None = None,
) -> FastAPI:
    paths = resolve_paths(runtime_root)
    bootstrap_workspace(paths)
    repository = ConfigRepository(paths.config_path)
    persona = PersonaService(paths.persona_path)
    persona.load()
    client_factory = model_client_factory or (lambda server, resolved_paths: ModelServerClient(server=server, paths=resolved_paths))
    state = ApplicationState(
        paths=paths,
        repository=repository,
        config=repository.load(),
        persona=persona,
        model_client_factory=client_factory,
    )
    app = FastAPI(title="VirtualMate", docs_url=None, redoc_url=None)
    app.state.vsa = state

    @app.middleware("http")
    async def disable_ui_cache(request, call_next):
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/assets/"):
            response.headers["Cache-Control"] = "no-store, max-age=0"
        return response

    assets_dir = paths.web_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/", response_class=HTMLResponse)
    def index():
        built_index = paths.web_dir / "index.html"
        if built_index.is_file():
            return FileResponse(built_index)
        return _INDEX_HTML

    @app.get("/api/bootstrap")
    def bootstrap() -> dict[str, Any]:
        return state.public_payload()

    @app.get("/api/avatar")
    def avatar():
        if paths.avatar_path.is_file():
            return FileResponse(paths.avatar_path)
        default_avatar = paths.web_dir / "assets" / "avatar-default.svg"
        if default_avatar.is_file():
            return FileResponse(default_avatar)
        return Response(_DEFAULT_AVATAR_SVG, media_type="image/svg+xml")

    @app.websocket("/ws")
    async def websocket_endpoint(socket: WebSocket) -> None:
        await socket.accept()
        try:
            while True:
                message = await socket.receive_json()
                request_id = str(message.get("request_id") or "") if isinstance(message, dict) else ""
                try:
                    if not request_id:
                        raise ValueError("request_id is required")
                    action = str(message.get("action") or "")
                    payload = message.get("payload") or {}
                    if not isinstance(payload, dict):
                        raise ValueError("payload must be an object")
                    if action in {"process_knowledge", "chat"}:
                        loop = asyncio.get_running_loop()

                        def progress(event: dict[str, object]) -> None:
                            future = asyncio.run_coroutine_threadsafe(
                                socket.send_json(
                                    {
                                        "request_id": request_id,
                                        "type": "progress",
                                        "payload": event,
                                    }
                                ),
                                loop,
                            )
                            future.result(timeout=30)

                        if action == "process_knowledge":
                            result = await asyncio.to_thread(state.process_knowledge, payload, progress)
                        else:
                            result = await asyncio.to_thread(state.chat, payload, progress)
                    else:
                        result = _dispatch(state, action, payload)
                    response = {"request_id": request_id, "type": "result", "ok": True, "payload": result}
                except Exception as exc:
                    response = {
                        "request_id": request_id,
                        "type": "result",
                        "ok": False,
                        "error": state.safe_error(exc),
                    }
                await socket.send_json(response)
        except WebSocketDisconnect:
            return

    return app


app = create_app()


__all__ = ["app", "create_app"]

