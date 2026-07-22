from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)


class ModelServerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=100)
    alias: str = Field(min_length=1, max_length=120)
    base_url: str
    api_key: str | None = None
    enabled: bool = True
    verify_ssl: bool = True
    use_corporate_ca: bool = False
    follow_redirects: bool = True
    proxy_enabled: bool = False
    http_proxy: str | None = None
    https_proxy: str | None = None
    no_proxy: str | None = None
    proxy_username: str | None = None
    proxy_password: str | None = None

    @field_validator("id", "alias")
    @classmethod
    def _strip_nonempty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be empty")
        return cleaned

    @field_validator("base_url")
    @classmethod
    def _valid_base_url(cls, value: str) -> str:
        cleaned = value.strip().rstrip("/")
        if cleaned != value.strip() or not _URL_RE.match(cleaned):
            raise ValueError("base_url must start with http:// or https:// and contain no whitespace")
        return cleaned

    @field_validator("api_key")
    @classmethod
    def _clean_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("http_proxy", "https_proxy", "no_proxy", "proxy_username", "proxy_password")
    @classmethod
    def _clean_optional_proxy_value(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    def public_dict(self) -> dict[str, Any]:
        payload = self.model_dump(exclude={"api_key", "proxy_password"})
        payload["has_api_key"] = bool(self.api_key)
        payload["has_proxy_password"] = bool(self.proxy_password)
        return payload


class ModelRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    server_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)


class RoleAssignments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chat: ModelRef | None = None
    embeddings: ModelRef | None = None


class RuntimeTuningConfig(BaseModel):
    """Operational settings persisted locally for constrained model servers."""

    embedding_batch_size: int = Field(default=32, ge=1, le=256)
    embedding_retry_attempts: int = Field(default=2, ge=0, le=5)
    embedding_retry_delay_seconds: float = Field(default=2.0, ge=0.0, le=60.0)
    embedding_inter_request_delay_ms: int = Field(default=0, ge=0, le=10_000)
    model_request_timeout_seconds: float = Field(default=60.0, ge=5.0, le=600.0)


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_servers: list[ModelServerConfig] = Field(default_factory=list)
    roles: RoleAssignments = Field(default_factory=RoleAssignments)
    model_traffic_logging: bool = False
    runtime_tuning: RuntimeTuningConfig = Field(default_factory=RuntimeTuningConfig)

    @field_validator("model_servers")
    @classmethod
    def _unique_servers(cls, servers: list[ModelServerConfig]) -> list[ModelServerConfig]:
        ids = [server.id for server in servers]
        if len(ids) != len(set(ids)):
            raise ValueError("model server ids must be unique")
        return servers

    def validate_role_references(self) -> None:
        available = {server.id for server in self.model_servers if server.enabled}
        for role_name in ("chat", "embeddings"):
            ref = getattr(self.roles, role_name)
            if ref is not None and ref.server_id not in available:
                raise ValueError(f"{role_name} role references missing or disabled server: {ref.server_id}")

    def public_dict(self) -> dict[str, Any]:
        return {
            "model_servers": [server.public_dict() for server in self.model_servers],
            "roles": self.roles.model_dump(mode="json"),
        }


class ConfigRepository:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> AppConfig:
        if not self.path.exists():
            return AppConfig()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Could not read application configuration: {exc}") from exc
        return AppConfig.model_validate(raw)

    def save(self, config: AppConfig) -> None:
        config.validate_role_references()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(config.model_dump(mode="json"), ensure_ascii=False, indent=2)
        self.path.write_text(serialized + "\n", encoding="utf-8")


__all__ = [
    "AppConfig",
    "ConfigRepository",
    "ModelRef",
    "ModelServerConfig",
    "RoleAssignments",
    "RuntimeTuningConfig",
]
