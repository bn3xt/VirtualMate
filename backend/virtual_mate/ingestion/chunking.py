"""Structured document chunking adapted from Substrate's proven LlamaIndex pipeline.

This standalone copy intentionally depends only on ``llama-index-core`` and does
not import the Substrate runtime. Markdown structure is parsed first and long
sections are then split with LlamaIndex's sentence-aware splitter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from llama_index.core.node_parser import MarkdownNodeParser, SentenceSplitter, TokenTextSplitter
from llama_index.core.schema import Document
from llama_index.core.utils import get_tokenizer


_LEADING_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*(?:\r?\n)+", re.DOTALL)


def tokenize(text: str) -> list[int]:
    return list(get_tokenizer()(str(text or "")))


def estimate_tokens(text: str) -> int:
    return len(tokenize(text))


@dataclass(frozen=True, slots=True)
class ChunkDraft:
    text: str
    heading: str | None


def _heading_and_body(text: str, metadata: dict[str, object]) -> tuple[str | None, str]:
    content = str(text or "").strip()
    match = _LEADING_HEADING_RE.match(content)
    if match:
        return match.group(1).strip(), content[match.end() :].strip()
    header_path = str(metadata.get("header_path") or "").strip("/").strip()
    heading = header_path.split("/")[-1].strip() if header_path else None
    return heading or None, content


def _split_section(text: str, *, chunk_size: int, overlap: int) -> list[str]:
    if estimate_tokens(text) <= chunk_size:
        return [text.strip()] if text.strip() else []
    try:
        return [
            piece.strip()
            for piece in SentenceSplitter(chunk_size=chunk_size, chunk_overlap=overlap).split_text(text)
            if piece.strip()
        ]
    except Exception:
        return [
            piece.strip()
            for piece in TokenTextSplitter(chunk_size=chunk_size, chunk_overlap=overlap).split_text(text)
            if piece.strip()
        ]


def chunk_markdown(text: str, *, chunk_size: int = 700, overlap: int = 100) -> list[ChunkDraft]:
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be non-negative and smaller than chunk_size")
    body = str(text or "").strip()
    if not body:
        return []

    document = Document(text=body)
    try:
        nodes = MarkdownNodeParser().get_nodes_from_documents([document])
    except Exception:
        nodes = []
    if not nodes:
        nodes = [document]

    chunks: list[ChunkDraft] = []
    for node in nodes:
        try:
            content = node.get_content(metadata_mode="none")
            metadata = dict(getattr(node, "metadata", {}) or {})
        except Exception:
            content = str(getattr(node, "text", "") or "")
            metadata = {}
        heading, section = _heading_and_body(content, metadata)
        for piece in _split_section(section, chunk_size=chunk_size, overlap=overlap):
            chunks.append(ChunkDraft(text=piece, heading=heading))
    return chunks


__all__ = ["ChunkDraft", "chunk_markdown", "estimate_tokens", "tokenize"]

