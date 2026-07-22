from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any


_SEARCH_TOKEN_RE = re.compile(r"[\w-]+", re.UNICODE)


class CorpusStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    relative_path TEXT NOT NULL UNIQUE,
                    filename TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    chunk_index INTEGER NOT NULL,
                    heading TEXT,
                    text TEXT NOT NULL,
                    UNIQUE(document_id, chunk_index)
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    chunk_id UNINDEXED,
                    text,
                    heading,
                    filename
                );
                """
            )

    def clear(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM chunks_fts")
            connection.execute("DELETE FROM chunks")
            connection.execute("DELETE FROM documents")

    def add_document(self, *, document_id: str, relative_path: str, filename: str, chunks: list[dict[str, Any]]) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO documents(id, relative_path, filename) VALUES (?, ?, ?)",
                (document_id, relative_path, filename),
            )
            for chunk in chunks:
                connection.execute(
                    "INSERT INTO chunks(id, document_id, chunk_index, heading, text) VALUES (?, ?, ?, ?, ?)",
                    (chunk["id"], document_id, chunk["chunk_index"], chunk.get("heading"), chunk["text"]),
                )
                connection.execute(
                    "INSERT INTO chunks_fts(chunk_id, text, heading, filename) VALUES (?, ?, ?, ?)",
                    (chunk["id"], chunk["text"], chunk.get("heading") or "", filename),
                )

    def document_count(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0])

    def chunk_count(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])

    def search_lexical(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        tokens = [token for token in _SEARCH_TOKEN_RE.findall(query) if token]
        if not tokens:
            return []
        expression = " OR ".join(f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT c.id, c.document_id, c.chunk_index, c.heading, c.text,
                       d.relative_path, d.filename, bm25(chunks_fts) AS rank
                FROM chunks_fts
                JOIN chunks c ON c.id = chunks_fts.chunk_id
                JOIN documents d ON d.id = c.document_id
                WHERE chunks_fts MATCH ?
                ORDER BY rank ASC
                LIMIT ?
                """,
                (expression, int(limit)),
            ).fetchall()
        return [{**dict(row), "score": 1.0 / (1.0 + abs(float(row["rank"] or 0.0)))} for row in rows]

    def get_chunk(self, chunk_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT c.id, c.document_id, c.chunk_index, c.heading, c.text,
                       d.relative_path, d.filename
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE c.id = ?
                """,
                (chunk_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_neighbors(self, document_id: str, chunk_index: int, *, window: int) -> list[dict[str, Any]]:
        low = int(chunk_index) - max(0, int(window))
        high = int(chunk_index) + max(0, int(window))
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT c.id, c.document_id, c.chunk_index, c.heading, c.text,
                       d.relative_path, d.filename
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE c.document_id = ? AND c.chunk_index BETWEEN ? AND ? AND c.chunk_index <> ?
                ORDER BY c.chunk_index
                """,
                (document_id, low, high, int(chunk_index)),
            ).fetchall()
        return [dict(row) for row in rows]


class ChromaStore:
    COLLECTION = "virtual-self-knowledge"

    def __init__(self, path: Path) -> None:
        from chromadb import PersistentClient
        from chromadb.config import Settings

        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.client = PersistentClient(
            path=str(self.path),
            settings=Settings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            self.COLLECTION,
            embedding_function=None,
            metadata={"hnsw:space": "cosine"},
        )

    def clear(self) -> None:
        try:
            self.client.delete_collection(self.COLLECTION)
        except Exception:
            pass
        self.collection = self.client.get_or_create_collection(
            self.COLLECTION,
            embedding_function=None,
            metadata={"hnsw:space": "cosine"},
        )

    def add(self, *, chunks: list[dict[str, Any]], embeddings: list[list[float]]) -> None:
        if not chunks:
            return
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings length mismatch")
        self.collection.add(
            ids=[str(chunk["id"]) for chunk in chunks],
            documents=[str(chunk["text"]) for chunk in chunks],
            embeddings=embeddings,
            metadatas=[
                {
                    "document_id": str(chunk["document_id"]),
                    "relative_path": str(chunk["relative_path"]),
                    "filename": str(chunk["filename"]),
                    "chunk_index": int(chunk["chunk_index"]),
                    "heading": str(chunk.get("heading") or ""),
                }
                for chunk in chunks
            ],
        )

    def count(self) -> int:
        return int(self.collection.count())

    def all_metadata(self) -> list[dict[str, Any]]:
        result = self.collection.get(include=["metadatas"])
        return [dict(item or {}) for item in (result.get("metadatas") or [])]

    def query(self, embedding: list[float], *, limit: int) -> list[dict[str, Any]]:
        count = self.count()
        if count <= 0:
            return []
        result = self.collection.query(
            query_embeddings=[embedding],
            n_results=min(max(1, int(limit)), count),
            include=["metadatas", "distances"],
        )
        ids = (result.get("ids") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        return [
            {
                "id": str(identifier),
                "metadata": dict(metadatas[index] or {}) if index < len(metadatas) else {},
                "distance": float(distances[index]) if index < len(distances) else None,
            }
            for index, identifier in enumerate(ids)
        ]


__all__ = ["ChromaStore", "CorpusStore"]
