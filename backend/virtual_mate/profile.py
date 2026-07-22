from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class RetrievalProfile:
    id: str
    semantic_top_k: int
    lexical_top_k: int
    candidate_pool_max: int
    rrf_k: int
    semantic_weight: float
    lexical_weight: float
    primary_hits: int
    max_primary_hits_per_document: int
    neighbor_window: int
    evidence_token_budget: int
    answer_token_budget: int
    conversation_token_budget: int
    minimum_chat_model_context: int
    reranker: str | None

    def public_dict(self) -> dict[str, object]:
        return asdict(self)


PERSONAL_LEGACY_PROFILE = RetrievalProfile(
    id="personal_legacy_v1",
    semantic_top_k=40,
    lexical_top_k=40,
    candidate_pool_max=80,
    rrf_k=60,
    semantic_weight=0.50,
    lexical_weight=0.50,
    primary_hits=14,
    max_primary_hits_per_document=3,
    neighbor_window=1,
    evidence_token_budget=14_000,
    answer_token_budget=2_500,
    conversation_token_budget=3_000,
    minimum_chat_model_context=32_768,
    reranker=None,
)


__all__ = ["PERSONAL_LEGACY_PROFILE", "RetrievalProfile"]

