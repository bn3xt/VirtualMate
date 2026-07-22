from __future__ import annotations

import json
from pathlib import Path

import pytest
import virtual_mate.paths as paths_module

from virtual_mate.config import (
    AppConfig,
    ConfigRepository,
    ModelRef,
    ModelServerConfig,
    RoleAssignments,
    RuntimeTuningConfig,
)
from virtual_mate.paths import bootstrap_workspace, resolve_paths
from virtual_mate.profile import PERSONAL_LEGACY_PROFILE


def test_portable_paths_are_fixed_beneath_runtime_root(tmp_path: Path) -> None:
    paths = resolve_paths(tmp_path)

    assert paths.runtime_root == tmp_path.resolve()
    assert paths.workspace_dir == tmp_path.resolve() / "workspace"
    assert paths.knowledge_dir == tmp_path.resolve() / "workspace" / "knowledge"
    assert paths.persona_path == tmp_path.resolve() / "workspace" / "persona.md"
    assert paths.avatar_path == tmp_path.resolve() / "workspace" / "avatar.png"
    assert paths.corporate_ca_path == tmp_path.resolve() / "workspace" / "corporate-ca.pem"
    assert paths.data_dir == tmp_path.resolve() / "data"
    assert paths.config_path == tmp_path.resolve() / "data" / "config.json"
    assert paths.database_path == tmp_path.resolve() / "data" / "corpus.db"
    assert paths.chroma_dir == tmp_path.resolve() / "data" / "chroma"
    assert paths.model_traffic_log_path == tmp_path.resolve() / "data" / "logs" / "model-traffic.jsonl"
    assert paths.web_dir == tmp_path.resolve() / "frontend" / "dist"


def test_frozen_runtime_reads_frontend_from_pyinstaller_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = tmp_path / "_internal"
    (bundle / "web").mkdir(parents=True)
    monkeypatch.setattr(paths_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(paths_module.sys, "_MEIPASS", str(bundle), raising=False)

    paths = resolve_paths(tmp_path / "portable")

    assert paths.web_dir == bundle / "web"


def test_workspace_bootstrap_creates_only_required_seed_files(tmp_path: Path) -> None:
    paths = resolve_paths(tmp_path)
    bootstrap_workspace(paths)

    assert paths.knowledge_dir.is_dir()
    assert paths.data_dir.is_dir()
    assert paths.logs_dir.is_dir()
    assert paths.persona_path.is_file()
    assert "persona" in paths.persona_path.read_text(encoding="utf-8").lower()
    assert not paths.corporate_ca_path.exists()


def test_bootstrap_does_not_overwrite_existing_persona(tmp_path: Path) -> None:
    paths = resolve_paths(tmp_path)
    paths.workspace_dir.mkdir(parents=True)
    paths.persona_path.write_text("# Existing\n\nKeep me.", encoding="utf-8")

    bootstrap_workspace(paths)

    assert paths.persona_path.read_text(encoding="utf-8") == "# Existing\n\nKeep me."


def test_config_repository_round_trips_multiple_servers_and_independent_roles(tmp_path: Path) -> None:
    repo = ConfigRepository(resolve_paths(tmp_path).config_path)
    config = AppConfig(
        model_servers=[
            ModelServerConfig(id="or", alias="OpenRouter", base_url="https://openrouter.ai/api/v1", api_key="secret-a"),
            ModelServerConfig(id="emb", alias="Embeddings", base_url="http://127.0.0.1:8110/v1", api_key="secret-b"),
        ],
        roles=RoleAssignments(
            chat=ModelRef(server_id="or", model_id="mistralai/ministral-14b-2512"),
            embeddings=ModelRef(server_id="emb", model_id="Alibaba-NLP/gte-multilingual-base"),
        ),
    )

    repo.save(config)
    loaded = repo.load()

    assert loaded == config
    raw = json.loads(repo.path.read_text(encoding="utf-8"))
    assert len(raw["model_servers"]) == 2
    assert raw["roles"]["chat"]["server_id"] == "or"
    assert raw["roles"]["embeddings"]["server_id"] == "emb"


@pytest.mark.parametrize("base_url", ["openrouter.ai/v1", " ftp://host/v1", "https://bad host/v1"])
def test_model_server_rejects_invalid_urls(base_url: str) -> None:
    with pytest.raises(ValueError):
        ModelServerConfig(id="server", alias="Server", base_url=base_url)


def test_public_config_redacts_api_keys() -> None:
    config = AppConfig(
        model_servers=[ModelServerConfig(id="s", alias="Server", base_url="https://example.test/v1", api_key="top-secret", proxy_password="proxy-secret")]
    )

    public = config.public_dict()

    assert public["model_servers"][0]["has_api_key"] is True
    assert public["model_servers"][0]["has_proxy_password"] is True
    assert "api_key" not in public["model_servers"][0]
    assert "top-secret" not in json.dumps(public)
    assert "proxy-secret" not in json.dumps(public)


def test_runtime_tuning_defaults_are_safe_for_limited_embeddings_servers() -> None:
    tuning = AppConfig().runtime_tuning

    assert tuning.embedding_batch_size == 32
    assert tuning.embedding_retry_attempts == 2
    assert tuning.embedding_retry_delay_seconds == 2.0
    assert tuning.embedding_inter_request_delay_ms == 0
    assert tuning.model_request_timeout_seconds == 60.0

    with pytest.raises(ValueError):
        RuntimeTuningConfig(embedding_batch_size=0)


def test_role_validation_requires_enabled_discovered_server_references() -> None:
    config = AppConfig(
        model_servers=[ModelServerConfig(id="s", alias="Server", base_url="https://example.test/v1")],
        roles=RoleAssignments(chat=ModelRef(server_id="missing", model_id="model")),
    )

    with pytest.raises(ValueError, match="missing"):
        config.validate_role_references()


def test_fixed_profile_matches_approved_lightweight_parameters() -> None:
    profile = PERSONAL_LEGACY_PROFILE

    assert profile.id == "personal_legacy_v1"
    assert profile.semantic_top_k == 40
    assert profile.lexical_top_k == 40
    assert profile.candidate_pool_max == 80
    assert profile.rrf_k == 60
    assert profile.semantic_weight == 0.5
    assert profile.lexical_weight == 0.5
    assert profile.primary_hits == 14
    assert profile.max_primary_hits_per_document == 3
    assert profile.neighbor_window == 1
    assert profile.evidence_token_budget == 14_000
    assert profile.answer_token_budget == 2_500
    assert profile.conversation_token_budget == 3_000
    assert profile.minimum_chat_model_context == 32_768
    assert profile.reranker is None

