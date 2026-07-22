from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from ..paths import RuntimePaths
from ..storage import ChromaStore, CorpusStore
from .chunking import chunk_markdown
from .extraction import ExtractionError, extract_document


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class ProcessingError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ProcessingResult:
    ok: bool
    files_discovered: int
    documents_processed: int
    chunks_generated: int
    elapsed_seconds: float
    errors: list[str] = field(default_factory=list)


class KnowledgeProcessor:
    def __init__(
        self,
        *,
        paths: RuntimePaths,
        corpus: CorpusStore,
        vectors: ChromaStore,
        embedder: Embedder,
        progress: Callable[[dict[str, object]], None] | None = None,
        embedding_batch_size: int = 64,
    ) -> None:
        self.paths = paths
        self.corpus = corpus
        self.vectors = vectors
        self.embedder = embedder
        self.progress = progress
        self.embedding_batch_size = max(1, int(embedding_batch_size))

    def _emit(self, **payload: object) -> None:
        if self.progress:
            self.progress(payload)

    def process(self) -> ProcessingResult:
        started = time.perf_counter()
        self._emit(phase="cleaning", current=0, total=0)
        self.vectors.clear()
        self.corpus.clear()
        sources = sorted(
            path
            for path in self.paths.knowledge_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in {".md", ".docx"}
        )
        errors: list[str] = []
        processed = 0
        chunks_generated = 0
        try:
            for source_index, source in enumerate(sources, start=1):
                relative = source.relative_to(self.paths.knowledge_dir).as_posix()
                self._emit(
                    phase="extracting",
                    current=source_index,
                    total=len(sources),
                    document=relative,
                    chunks=chunks_generated,
                )
                try:
                    extracted = extract_document(source)
                except ExtractionError as exc:
                    errors.append(str(exc))
                    continue
                drafts = chunk_markdown(extracted.text, chunk_size=700, overlap=100)[:5_000]
                if not drafts:
                    errors.append(f"No usable text extracted from {relative}")
                    continue
                document_id = relative
                chunks = [
                    {
                        "id": f"{document_id}:{index}",
                        "document_id": document_id,
                        "relative_path": relative,
                        "filename": source.name,
                        "chunk_index": index,
                        "heading": draft.heading,
                        "text": draft.text,
                    }
                    for index, draft in enumerate(drafts)
                ]
                self._emit(
                    phase="chunked",
                    current=source_index,
                    total=len(sources),
                    document=relative,
                    documents_processed=processed,
                    chunks_generated=chunks_generated,
                    document_chunks=len(chunks),
                    chunks_expected=chunks_generated + len(chunks),
                )
                embeddings: list[list[float]] = []
                for start in range(0, len(chunks), self.embedding_batch_size):
                    batch = chunks[start : start + self.embedding_batch_size]
                    self._emit(
                        phase="vectorizing",
                        current=source_index,
                        total=len(sources),
                        document=relative,
                        documents_processed=processed,
                        chunks_generated=chunks_generated,
                        document_chunks=len(chunks),
                        vectorization_current=start,
                        vectorization_total=len(chunks),
                        vectorized_chunks=chunks_generated + start,
                    )
                    embeddings.extend(self.embedder.embed([str(chunk["text"]) for chunk in batch]))
                    self._emit(
                        phase="vectorizing",
                        current=source_index,
                        total=len(sources),
                        document=relative,
                        documents_processed=processed,
                        chunks_generated=chunks_generated,
                        document_chunks=len(chunks),
                        vectorization_current=start + len(batch),
                        vectorization_total=len(chunks),
                        vectorized_chunks=chunks_generated + start + len(batch),
                    )
                if len(embeddings) != len(chunks):
                    raise ValueError("Embedding provider returned an unexpected vector count")
                self.corpus.add_document(
                    document_id=document_id,
                    relative_path=relative,
                    filename=source.name,
                    chunks=chunks,
                )
                self.vectors.add(chunks=chunks, embeddings=embeddings)
                processed += 1
                chunks_generated += len(chunks)
                self._emit(
                    phase="indexed",
                    current=source_index,
                    total=len(sources),
                    document=relative,
                    documents_processed=processed,
                    chunks_generated=chunks_generated,
                )
        except Exception as exc:
            self.corpus.clear()
            self.vectors.clear()
            raise ProcessingError(
                f"Knowledge processing failed and the rebuilt index is incomplete; run Process knowledge again: {exc}"
            ) from exc
        elapsed = time.perf_counter() - started
        result = ProcessingResult(
            ok=not errors,
            files_discovered=len(sources),
            documents_processed=processed,
            chunks_generated=chunks_generated,
            elapsed_seconds=elapsed,
            errors=errors,
        )
        self._emit(
            phase="complete",
            current=processed,
            total=len(sources),
            documents_processed=processed,
            chunks_generated=chunks_generated,
            ok=result.ok,
        )
        return result


__all__ = ["KnowledgeProcessor", "ProcessingError", "ProcessingResult"]
