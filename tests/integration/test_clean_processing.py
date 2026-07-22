from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from virtual_mate.ingestion.processor import KnowledgeProcessor, ProcessingError
from virtual_mate.paths import bootstrap_workspace, resolve_paths
from virtual_mate.retrieval import RetrievalEngine
from virtual_mate.storage import ChromaStore, CorpusStore


class FakeEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), float(index + 1), 0.5] for index, text in enumerate(texts)]


class FailingEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("provider unavailable")


def _processor(tmp_path: Path, embedder=None) -> tuple[KnowledgeProcessor, CorpusStore, ChromaStore]:
    paths = resolve_paths(tmp_path)
    bootstrap_workspace(paths)
    corpus = CorpusStore(paths.database_path)
    vectors = ChromaStore(paths.chroma_dir)
    processor = KnowledgeProcessor(paths=paths, corpus=corpus, vectors=vectors, embedder=embedder or FakeEmbedder())
    return processor, corpus, vectors


def test_clean_processing_indexes_markdown_and_docx(tmp_path: Path) -> None:
    processor, corpus, vectors = _processor(tmp_path)
    knowledge = resolve_paths(tmp_path).knowledge_dir
    (knowledge / "architecture.md").write_text("# Architecture\n\nRelay Envelope v3 connects Northstar and Meridian.", encoding="utf-8")

    result = processor.process()

    assert result.ok is True
    assert result.files_discovered == 1
    assert result.documents_processed == 1
    assert result.chunks_generated == 1
    assert corpus.document_count() == 1
    assert corpus.chunk_count() == 1
    assert vectors.count() == 1
    assert corpus.search_lexical("Relay Envelope", limit=5)[0]["relative_path"] == "architecture.md"


def test_second_processing_run_removes_first_corpus_from_both_stores(tmp_path: Path) -> None:
    processor, corpus, vectors = _processor(tmp_path)
    knowledge = resolve_paths(tmp_path).knowledge_dir
    first = knowledge / "cycle_a.md"
    first.write_text("# Cycle\n\nORION-CYCLE-A ALPHAONLY.", encoding="utf-8")
    processor.process()

    first.unlink()
    (knowledge / "cycle_b.md").write_text("# Cycle\n\nORION-CYCLE-B BETAONLY.", encoding="utf-8")
    processor.process()

    assert corpus.search_lexical("ALPHAONLY", limit=10) == []
    assert corpus.search_lexical("BETAONLY", limit=10)
    all_vectors = vectors.all_metadata()
    assert {item["relative_path"] for item in all_vectors} == {"cycle_b.md"}


def test_processing_failure_is_explicit_after_cleaning_previous_index(tmp_path: Path) -> None:
    processor, corpus, vectors = _processor(tmp_path)
    knowledge = resolve_paths(tmp_path).knowledge_dir
    (knowledge / "source.md").write_text("# Source\n\nInitial searchable content.", encoding="utf-8")
    processor.process()
    failing = KnowledgeProcessor(
        paths=resolve_paths(tmp_path), corpus=corpus, vectors=vectors, embedder=FailingEmbedder()
    )

    with pytest.raises(ProcessingError, match="incomplete"):
        failing.process()

    assert corpus.chunk_count() == 0
    assert vectors.count() == 0


def test_schema_contains_no_incremental_or_checksum_state(tmp_path: Path) -> None:
    _processor(tmp_path)
    database = resolve_paths(tmp_path).database_path
    with sqlite3.connect(database) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        columns = {
            row[1]
            for table in ("documents", "chunks")
            for row in connection.execute(f"PRAGMA table_info({table})")
        }

    assert "ingestion_runs" not in tables
    assert not {"checksum", "sha256", "state", "version", "fingerprint"} & columns


def test_real_chroma_and_fts5_feed_hybrid_retrieval(tmp_path: Path) -> None:
    class KeywordEmbedder:
        def embed(self, texts: list[str]) -> list[list[float]]:
            vectors: list[list[float]] = []
            for text in texts:
                lowered = text.lower()
                vectors.append(
                    [
                        1.0 if "relay" in lowered else 0.0,
                        1.0 if "deployment" in lowered else 0.0,
                        0.1,
                    ]
                )
            return vectors

    paths = resolve_paths(tmp_path)
    bootstrap_workspace(paths)
    (paths.knowledge_dir / "architecture.md").write_text(
        "# Architecture\n\nRelay Envelope v3 connects Northstar and Meridian.", encoding="utf-8"
    )
    (paths.knowledge_dir / "operations.md").write_text(
        "# Deployment\n\nThe deployment window starts Tuesday at 07:30 CET.", encoding="utf-8"
    )
    corpus = CorpusStore(paths.database_path)
    vectors = ChromaStore(paths.chroma_dir)
    embedder = KeywordEmbedder()
    KnowledgeProcessor(paths=paths, corpus=corpus, vectors=vectors, embedder=embedder).process()

    result = RetrievalEngine(corpus=corpus, vectors=vectors, embedder=embedder).retrieve(
        "What does the relay connect?"
    )

    assert result.evidence
    assert result.evidence[0].relative_path == "architecture.md"
    assert "Northstar" in result.evidence[0].text
    assert result.diagnostics["semantic_hits"] >= 1
    assert result.diagnostics["lexical_hits"] >= 1
    assert result.diagnostics["evidence_tokens"] <= 14_000

