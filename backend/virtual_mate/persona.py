from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .ingestion.chunking import estimate_tokens


class PersonaError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PersonaSnapshot:
    text: str
    estimated_tokens: int

    @property
    def over_budget(self) -> bool:
        return self.estimated_tokens > 2_000


class PersonaService:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._active: PersonaSnapshot | None = None

    @property
    def active(self) -> PersonaSnapshot | None:
        return self._active

    def load(self) -> PersonaSnapshot:
        if not self.path.is_file():
            raise PersonaError(f"Persona file is missing: {self.path.name}")
        try:
            text = self.path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError as exc:
            raise PersonaError(f"Could not read persona: {exc}") from exc
        if not text:
            raise PersonaError("Persona file is empty")
        self._active = PersonaSnapshot(text=text, estimated_tokens=estimate_tokens(text))
        return self._active

    def reload(self) -> PersonaSnapshot:
        return self.load()


__all__ = ["PersonaError", "PersonaService", "PersonaSnapshot"]

