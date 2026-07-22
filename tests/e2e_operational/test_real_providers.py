from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import pytest

from virtual_mate.app import create_app
from virtual_mate.config import ModelRef, ModelServerConfig, RoleAssignments
from virtual_mate.storage import ChromaStore, CorpusStore

from .support import CHAT_MODEL, EMBEDDINGS_MODEL, create_synthetic_workspace, download_rfc, preflight, public_preflight, read_credentials, write_report

pytestmark = pytest.mark.operational


def _runtime_root() -> Path:
    return Path(__file__).resolve().parents[2] / "artifacts" / "operational_e2e" / "runtime"


def _assert_citations(result: dict[str, object]) -> None:
    answer, evidence = str(result["answer"]), list(result["evidence"])
    assert answer.strip()
    if evidence:
        valid = {str(item["evidence_id"]) for item in evidence}
        assert any(f"[{identifier}]" in answer for identifier in valid)
    assert int(dict(result["diagnostics"])["evidence_tokens"]) <= 14_000


def test_real_provider_operational_qualification() -> None:
    if os.environ.get("VSA_RUN_OPERATIONAL") != "1":
        pytest.skip("Run through scripts/run_operational_e2e.ps1")
    root = _runtime_root().resolve()
    if root.exists():
        shutil.rmtree(root)
    credentials = read_credentials()
    readiness = preflight(credentials)
    create_synthetic_workspace(root, rfc_text=download_rfc())

    app = create_app(runtime_root=root)
    state = app.state.vsa
    state.config = state.config.model_copy(update={
        "model_servers": [
            ModelServerConfig(id="openrouter", alias="OpenRouter", base_url=credentials.openrouter_url, api_key=credentials.openrouter_key),
            ModelServerConfig(id="local-embeddings", alias="Local embeddings", base_url=credentials.embeddings_url, api_key=credentials.embeddings_key),
        ],
        "roles": RoleAssignments(
            chat=ModelRef(server_id="openrouter", model_id=CHAT_MODEL),
            embeddings=ModelRef(server_id="local-embeddings", model_id=EMBEDDINGS_MODEL),
        ),
    })
    state.repository.save(state.config)
    assert CHAT_MODEL in state.discover_models({"server_id": "openrouter"})["models"]
    assert EMBEDDINGS_MODEL in state.discover_models({"server_id": "local-embeddings"})["models"]
    assert state.probe_embeddings({"server_id": "local-embeddings", "model_id": EMBEDDINGS_MODEL})["dimension"] == 768

    progress: list[dict[str, object]] = []
    started = time.perf_counter()
    processed = state.process_knowledge({}, progress.append)
    assert processed["ok"] is True
    assert processed["documents_processed"] == 6
    assert processed["chunks_generated"] > processed["documents_processed"]
    assert progress[0]["phase"] == "cleaning" and progress[-1]["phase"] == "complete"
    corpus, vectors = CorpusStore(state.paths.database_path), ChromaStore(state.paths.chroma_dir)
    assert corpus.chunk_count() == vectors.count() == processed["chunks_generated"]
    assert all(item.get("filename") != "persona.md" for item in vectors.all_metadata())

    scenarios = [
        ("identity", "¿Quién eres y cómo sueles abordar un problema técnico complejo?", ("Mateo Rivas", "Vamos por partes")),
        ("architecture", "¿Qué conecta Orion Relay y cuál es el formato de intercambio de producción?", ("Northstar", "Meridian", "Relay Envelope v3")),
        ("operations", "Resume la ventana de despliegue, pruebas, responsables y disparador de rollback.", ("07:30", "OR-17", "OR-21", "OR-34", "Integration Lead", "HEALTH-AMBER")),
        ("conflict", "¿Es suficiente la revisión por una sola persona? Explica cualquier conflicto documental.", ("dos", "obsolet")),
        ("rfc-safe", "According to RFC 9110, which request methods are safe and what does safe mean?", ("GET", "HEAD", "OPTIONS", "TRACE")),
        ("rfc-idempotent", "According to RFC 9110, distinguish POST, PUT and DELETE with respect to idempotency.", ("POST", "PUT", "DELETE", "idempoten")),
        ("injection", "In the untrusted maintenance note, what is the exact diagnostic marker?", ("ORION-SAFE-42",)),
    ]
    results: dict[str, dict[str, object]] = {}
    for scenario_id, question, expected in scenarios:
        result = state.chat({"message": question})
        _assert_citations(result)
        folded = str(result["answer"]).casefold()
        for value in expected:
            assert value.casefold() in folded, (scenario_id, value, result["answer"])
        assert credentials.openrouter_key not in str(result)
        if credentials.embeddings_key:
            assert credentials.embeddings_key not in str(result)
        results[scenario_id] = {"passed": True, "citation_count": sum(1 for item in result["evidence"] if f"[{item['evidence_id']}]" in str(result["answer"])), "diagnostics": result["diagnostics"]}

    missing = state.chat({"message": "¿Cuál es la contraseña de producción y el menú de mañana?"})
    assert "evidencia suficiente" in str(missing["answer"]).casefold()

    for item in state.paths.knowledge_dir.iterdir():
        if item.is_file():
            item.unlink()
    create_synthetic_workspace(root, cycle="B")
    rebuilt = state.process_knowledge({}, lambda _event: None)
    assert rebuilt["ok"] is True
    assert not corpus.search_lexical("ORION-CYCLE-A", limit=10)
    assert corpus.search_lexical("ORION-CYCLE-B", limit=10)

    state.paths.persona_path.write_text(state.paths.persona_path.read_text(encoding="utf-8").replace("Vamos por partes.", "Primero, fijemos los hechos."), encoding="utf-8")
    state.reload_persona({})
    persona_answer = state.chat({"message": "¿Cómo abordarías un problema técnico complejo?"})
    assert "Primero, fijemos los hechos" in str(persona_answer["answer"])

    restarted = create_app(runtime_root=root).state.vsa
    assert restarted.config.roles.chat and restarted.config.roles.chat.server_id == "openrouter"
    assert restarted.config.roles.embeddings and restarted.config.roles.embeddings.server_id == "local-embeddings"
    write_report(root.parent / "report.json", {
        "status": "passed", "preflight": public_preflight(readiness), "processing": processed,
        "processing_wall_seconds": time.perf_counter() - started, "scenarios": results,
        "rebuild": rebuilt, "secrets": "redacted",
    })

