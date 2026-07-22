from __future__ import annotations

from pathlib import Path

from e2e_operational.support import create_synthetic_workspace, read_credentials


def test_operational_credentials_are_redacted(tmp_path: Path) -> None:
    key = tmp_path / "KEY.txt"
    key.write_text("secret-chat\nhttps://chat.example/v1\nhttp://127.0.0.1:8110\nsecret-embed\n", encoding="utf-8")
    credentials = read_credentials(key)
    assert credentials.embeddings_url == "http://127.0.0.1:8110/v1"
    assert "secret-chat" not in repr(credentials)
    assert "secret-embed" not in repr(credentials)


def test_synthetic_workspace_has_fixed_supported_sources(tmp_path: Path) -> None:
    create_synthetic_workspace(tmp_path)
    knowledge = tmp_path / "workspace" / "knowledge"
    assert (tmp_path / "workspace" / "persona.md").is_file()
    assert sorted(path.suffix for path in knowledge.iterdir()) == [".docx", ".md", ".md", ".md", ".md"]
    assert "ORION-CYCLE-A" in (knowledge / "project_orion_architecture.md").read_text(encoding="utf-8")

