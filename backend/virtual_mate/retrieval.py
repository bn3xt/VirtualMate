from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Protocol

from .ingestion.chunking import estimate_tokens, tokenize
from .profile import PERSONAL_LEGACY_PROFILE, RetrievalProfile


class RetrievalEmbedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class RetrievalCorpus(Protocol):
    def search_lexical(self, query: str, *, limit: int) -> list[dict[str, Any]]: ...
    def get_chunk(self, chunk_id: str) -> dict[str, Any] | None: ...
    def get_neighbors(self, document_id: str, chunk_index: int, *, window: int) -> list[dict[str, Any]]: ...


class RetrievalVectors(Protocol):
    def query(self, embedding: list[float], *, limit: int) -> list[dict[str, Any]]: ...


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    id: str
    document_id: str
    chunk_index: int
    relative_path: str
    filename: str
    heading: str | None
    text: str
    score: float
    match_type: str
    evidence_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "document_id": self.document_id,
            "chunk_index": self.chunk_index,
            "relative_path": self.relative_path,
            "filename": self.filename,
            "heading": self.heading,
            "text": self.text,
            "score": self.score,
            "match_type": self.match_type,
            "evidence_id": self.evidence_id,
        }


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    evidence: list[RetrievedChunk]
    diagnostics: dict[str, Any]


def _chunk_from_dict(raw: dict[str, Any], *, score: float, match_type: str) -> RetrievedChunk:
    return RetrievedChunk(
        id=str(raw.get("id") or raw.get("chunk_id") or ""),
        document_id=str(raw.get("document_id") or ""),
        chunk_index=int(raw.get("chunk_index") or 0),
        relative_path=str(raw.get("relative_path") or ""),
        filename=str(raw.get("filename") or ""),
        heading=str(raw.get("heading") or "") or None,
        text=str(raw.get("text") or ""),
        score=float(score),
        match_type=match_type,
    )


def weighted_rrf(
    *,
    semantic: list[RetrievedChunk],
    lexical: list[RetrievedChunk],
    profile: RetrievalProfile,
) -> list[RetrievedChunk]:
    canonical: dict[str, RetrievedChunk] = {}
    scores: dict[str, float] = {}
    sources: dict[str, set[str]] = {}
    for source, items, weight in (
        ("semantic", semantic, profile.semantic_weight),
        ("lexical", lexical, profile.lexical_weight),
    ):
        for rank, item in enumerate(items, start=1):
            canonical.setdefault(item.id, item)
            scores[item.id] = scores.get(item.id, 0.0) + weight / (profile.rrf_k + rank)
            sources.setdefault(item.id, set()).add(source)
    fused = [
        replace(canonical[identifier], score=score, match_type="+".join(sorted(sources[identifier])))
        for identifier, score in scores.items()
    ]
    fused.sort(key=lambda item: item.score, reverse=True)
    return fused[: profile.candidate_pool_max]


def select_diverse_primary(
    candidates: list[RetrievedChunk],
    *,
    limit: int,
    max_per_document: int,
) -> list[RetrievedChunk]:
    selected: list[RetrievedChunk] = []
    deferred: list[RetrievedChunk] = []
    counts: dict[str, int] = {}
    for item in candidates:
        if len(selected) >= limit:
            break
        count = counts.get(item.document_id, 0)
        if count >= max_per_document:
            deferred.append(item)
            continue
        selected.append(item)
        counts[item.document_id] = count + 1
    for item in deferred:
        if len(selected) >= limit:
            break
        selected.append(item)
    return selected


def _substantial_overlap(left: str, right: str) -> bool:
    left_tokens = set(tokenize(left))
    right_tokens = set(tokenize(right))
    smallest = min(len(left_tokens), len(right_tokens))
    if smallest == 0:
        return False
    return len(left_tokens & right_tokens) / smallest >= 0.88


class RetrievalEngine:
    def __init__(
        self,
        *,
        corpus: RetrievalCorpus,
        vectors: RetrievalVectors,
        embedder: RetrievalEmbedder,
        profile: RetrievalProfile = PERSONAL_LEGACY_PROFILE,
    ) -> None:
        self.corpus = corpus
        self.vectors = vectors
        self.embedder = embedder
        self.profile = profile

    def _semantic(self, query: str) -> list[RetrievedChunk]:
        embeddings = self.embedder.embed([query])
        if len(embeddings) != 1:
            raise ValueError("Embedding provider returned an unexpected query vector count")
        hits: list[RetrievedChunk] = []
        for raw in self.vectors.query(embeddings[0], limit=self.profile.semantic_top_k):
            chunk_id = str(raw.get("id") or "")
            hydrated = self.corpus.get_chunk(chunk_id)
            if not hydrated:
                continue
            distance = raw.get("distance")
            score = max(0.0, 1.0 - float(distance)) if distance is not None else 0.0
            if score < 0.05:
                continue
            hits.append(_chunk_from_dict(hydrated, score=score, match_type="semantic"))
        return hits

    def _lexical(self, query: str) -> list[RetrievedChunk]:
        return [
            _chunk_from_dict(raw, score=float(raw.get("score") or 0.0), match_type="lexical")
            for raw in self.corpus.search_lexical(query, limit=self.profile.lexical_top_k)
        ]

    def retrieve(self, query: str) -> RetrievalResult:
        semantic = self._semantic(query)
        lexical = self._lexical(query)
        fused = weighted_rrf(semantic=semantic, lexical=lexical, profile=self.profile)
        primary = select_diverse_primary(
            fused,
            limit=self.profile.primary_hits,
            max_per_document=self.profile.max_primary_hits_per_document,
        )

        expanded: list[RetrievedChunk] = []
        seen_ids: set[str] = set()
        for item in primary:
            related = [item]
            for raw in self.corpus.get_neighbors(
                item.document_id,
                item.chunk_index,
                window=self.profile.neighbor_window,
            ):
                related.append(_chunk_from_dict(raw, score=item.score, match_type="neighbor"))
            related.sort(key=lambda candidate: (candidate.id != item.id, candidate.chunk_index))
            for candidate in related:
                if not candidate.id or candidate.id in seen_ids:
                    continue
                if any(_substantial_overlap(candidate.text, previous.text) for previous in expanded):
                    continue
                seen_ids.add(candidate.id)
                expanded.append(candidate)

        evidence: list[RetrievedChunk] = []
        evidence_tokens = 0
        for item in expanded:
            item_tokens = estimate_tokens(item.text) + estimate_tokens(item.heading or "") + 12
            if evidence_tokens + item_tokens > self.profile.evidence_token_budget:
                continue
            evidence_tokens += item_tokens
            evidence.append(replace(item, evidence_id=f"E{len(evidence) + 1}"))

        return RetrievalResult(
            evidence=evidence,
            diagnostics={
                "profile_id": self.profile.id,
                "fusion_strategy": "rrf",
                "semantic_hits": len(semantic),
                "lexical_hits": len(lexical),
                "fused_hits": len(fused),
                "primary_hits": len(primary),
                "expanded_hits": len(expanded),
                "evidence_hits": len(evidence),
                "evidence_tokens": evidence_tokens,
                "evidence_token_budget": self.profile.evidence_token_budget,
            },
        )


__all__ = [
    "RetrievedChunk",
    "RetrievalEngine",
    "RetrievalResult",
    "select_diverse_primary",
    "weighted_rrf",
]

