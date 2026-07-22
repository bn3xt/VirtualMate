from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


PERSONA_TEMPLATE = """# Persona

Describe the assistant identity, role, communication style, technical preferences,
opinions, characteristic phrases, and uncertainty behavior here.
"""


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    runtime_root: Path
    workspace_dir: Path
    knowledge_dir: Path
    persona_path: Path
    avatar_path: Path
    corporate_ca_path: Path
    data_dir: Path
    config_path: Path
    database_path: Path
    chroma_dir: Path
    logs_dir: Path
    model_traffic_log_path: Path
    web_dir: Path


def _default_runtime_root() -> Path:
    explicit = os.environ.get("VSA_RUNTIME_ROOT", "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def resolve_paths(runtime_root: str | Path | None = None) -> RuntimePaths:
    root = Path(runtime_root).expanduser().resolve() if runtime_root is not None else _default_runtime_root()
    workspace = root / "workspace"
    data = root / "data"
    portable_web = root / "web"
    source_web = root / "frontend" / "dist"
    bundled_web = Path(str(getattr(sys, "_MEIPASS", ""))) / "web" if getattr(sys, "frozen", False) else None
    explicit_web = os.environ.get("VSA_WEB_DIR", "").strip()
    return RuntimePaths(
        runtime_root=root,
        workspace_dir=workspace,
        knowledge_dir=workspace / "knowledge",
        persona_path=workspace / "persona.md",
        avatar_path=workspace / "avatar.png",
        corporate_ca_path=workspace / "corporate-ca.pem",
        data_dir=data,
        config_path=data / "config.json",
        database_path=data / "corpus.db",
        chroma_dir=data / "chroma",
        logs_dir=data / "logs",
        model_traffic_log_path=data / "logs" / "model-traffic.jsonl",
        web_dir=(
            Path(explicit_web).expanduser().resolve()
            if explicit_web
            else (
                bundled_web
                if bundled_web is not None and bundled_web.is_dir()
                else (portable_web if portable_web.is_dir() else source_web)
            )
        ),
    )


def bootstrap_workspace(paths: RuntimePaths) -> None:
    paths.knowledge_dir.mkdir(parents=True, exist_ok=True)
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)
    if not paths.persona_path.exists():
        paths.persona_path.write_text(PERSONA_TEMPLATE, encoding="utf-8")


__all__ = ["RuntimePaths", "bootstrap_workspace", "resolve_paths"]
