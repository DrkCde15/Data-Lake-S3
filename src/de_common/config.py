"""Centralized, env-based configuration. Missing required values fail fast."""

from __future__ import annotations

import os
from dataclasses import dataclass

from .errors import ConfigError


def _get(name: str, default: str = "", *, required: bool = False) -> str:
    value = os.environ.get(name, default).strip()
    if required and not value:
        raise ConfigError(f"missing required env var: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    """One settings object per process, built from the environment."""

    aws_profile: str = "local"
    aws_region: str = "sa-east-1"
    endpoint_url: str | None = None
    lake_bucket: str = "data-engineer-lab-local"
    env_name: str = "local"

    @classmethod
    def from_env(cls) -> Settings:
        endpoint = os.environ.get("AWS_ENDPOINT_URL", "").strip() or None
        return cls(
            aws_profile=os.environ.get("AWS_PROFILE", "local").strip() or "local",
            aws_region=os.environ.get("AWS_REGION", "sa-east-1").strip() or "sa-east-1",
            endpoint_url=endpoint,
            lake_bucket=_get("LAKE_BUCKET", "data-engineer-lab-local"),
            env_name=_get("ENV_NAME", "local"),
        )

    @property
    def is_local(self) -> bool:
        return self.endpoint_url is not None
