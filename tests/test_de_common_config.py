"""de_common (vendored) config tests — owned by project 01, reused by 02-04."""

import os

import pytest

from de_common.config import Settings
from de_common.errors import ConfigError


def test_from_env_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("AWS_PROFILE", "AWS_REGION", "AWS_ENDPOINT_URL", "LAKE_BUCKET", "ENV_NAME"):
        monkeypatch.delenv(var, raising=False)
    s = Settings.from_env()
    assert s.aws_region == "sa-east-1"
    assert s.endpoint_url is None
    assert not s.is_local


def test_from_env_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_ENDPOINT_URL", "http://127.0.0.1:4566")
    monkeypatch.setenv("LAKE_BUCKET", "my-bucket")
    s = Settings.from_env()
    assert s.is_local
    assert s.lake_bucket == "my-bucket"


def test_get_required_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    from de_common.config import _get

    monkeypatch.delenv("MISSING_VAR_XYZ", raising=False)
    with pytest.raises(ConfigError):
        _get("MISSING_VAR_XYZ", required=True)


def test_env_example_covers_settings() -> None:
    path = os.path.join(os.path.dirname(__file__), "..", ".env.example")
    with open(path) as fh:
        example = fh.read()
    for var in ("AWS_PROFILE", "AWS_REGION", "AWS_ENDPOINT_URL", "LAKE_BUCKET", "ENV_NAME"):
        assert var in example
