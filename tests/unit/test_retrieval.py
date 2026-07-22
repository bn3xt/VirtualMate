from __future__ import annotations

from dataclasses import replace

from virtual_mate.profile import PERSONAL_LEGACY_PROFILE
from virtual_mate.retrieval import (
    RetrievedChunk,
    RetrievalEngine,
    select_diverse_primary,
    weighted_rrf,
)


def _chunk(identifier: str, document: str, index: int, score: float, text: str | None = None) -> RetrievedChunk:
    return RetrievedChunk(
        id=identifier,
        document_id=document,
        chunk_index=index,
        relative_path=f"{document}.md",
        filename=f"{document}.md",
        heading="Section",
        text=text or f"Evidence {identifier}",
        score=score,
        match_type="test",
    )


def test_weighted_rrf_rewards_chunks_found_by_both_rankings() -> None:
    semantic = [_chunk("a", "a", 0, 0.9), _chunk("b", "b", 0, 0.8)]
    lexical = [_chunk("b", "b", 0, 12.0), _chunk("c", "c", 0, 10.0)]

    fused = weighted_rrf(semantic=semantic, lexical=lexical, profile=PERSONAL_LEGACY_PROFILE)

    assert [item.id for item in fused] == ["b", "a", "c"]
    assert fused[0].match_type == "lexical+semantic"


def test_primary_selection_adds_document_diversity_before_deferred_hits() -> None:
    candidates = [
        *[_chunk(f"a:{index}", "a", index, 1.0 - index / 100) for index in range(6)],
        _chunk("b:0", "b", 0, 0.8),
        _chunk("c:0", "c", 0, 0.7),
    ]

    selected = select_diverse_primary(candidates, limit=7, max_per_document=3)

    assert [item.id for item in selected[:5]] == ["a:0", "a:1", "a:2", "b:0", "c:0"]
    assert len(selected) == 7


class FakeEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]


class FakeVectors:
    def query(self, embedding: list[float], *, limit: int) -> list[dict]:
        return [
            {"id": "a:1", "distance": 0.1},
            {"id": "b:0", "distance": 0.2},
        ]


class FakeCorpus:
    def __init__(self) -> None:
        self.items = {
            "a:0": _chunk("a:0", "a", 0, 0.0, "Previous context."),
            "a:1": _chunk("a:1", "a", 1, 0.0, "Primary semantic and lexical evidence."),
            "a:2": _chunk("a:2", "a", 2, 0.0, "Following context."),
            "b:0": _chunk("b:0", "b", 0, 0.0, "Second document evidence."),
        }

    def search_lexical(self, query: str, *, limit: int) -> list[dict]:
        item = self.items.get("a:1")
        if item is None:
            return []
        return [{**item.as_dict(), "score": 5.0}]

    def get_chunk(self, chunk_id: str) -> dict | None:
        item = self.items.get(chunk_id)
        return item.as_dict() if item else None

    def get_neighbors(self, document_id: str, chunk_index: int, *, window: int) -> list[dict]:
        return [
            item.as_dict()
            for item in self.items.values()
            if item.document_id == document_id and 0 < abs(item.chunk_index - chunk_index) <= window
        ]


def test_retrieval_fuses_hydrates_expands_and_labels_evidence() -> None:
    engine = RetrievalEngine(corpus=FakeCorpus(), vectors=FakeVectors(), embedder=FakeEmbedder())

    result = engine.retrieve("primary evidence")

    assert [item.evidence_id for item in result.evidence] == ["E1", "E2", "E3", "E4"]
    assert result.evidence[0].id == "a:1"
    assert {item.id for item in result.evidence} == {"a:0", "a:1", "a:2", "b:0"}
    assert result.diagnostics["semantic_hits"] == 2
    assert result.diagnostics["lexical_hits"] == 1
    assert result.diagnostics["fusion_strategy"] == "rrf"
    assert result.diagnostics["evidence_tokens"] <= 14_000


def test_retrieval_never_exceeds_evidence_token_ceiling() -> None:
    corpus = FakeCorpus()
    large_text = " ".join(f"fact{index}" for index in range(690))
    corpus.items = {
        f"d{index}:0": _chunk(f"d{index}:0", f"d{index}", 0, 0.0, large_text)
        for index in range(30)
    }

    class ManyVectors:
        def query(self, embedding: list[float], *, limit: int) -> list[dict]:
            return [{"id": item_id, "distance": 0.1 + index / 1000} for index, item_id in enumerate(corpus.items)]

    engine = RetrievalEngine(corpus=corpus, vectors=ManyVectors(), embedder=FakeEmbedder())

    result = engine.retrieve("facts")

    assert result.diagnostics["evidence_tokens"] <= PERSONAL_LEGACY_PROFILE.evidence_token_budget
    assert len(result.evidence) < 30

