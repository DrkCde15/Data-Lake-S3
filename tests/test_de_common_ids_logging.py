"""de_common (vendored) ids + logging tests — owned by project 01."""

import json
import logging

import pytest

from de_common import ids
from de_common.logging import bind, get_logger


def test_idempotency_key_deterministic() -> None:
    payload = {"b": 2, "a": 1}
    assert ids.idempotency_key(payload) == ids.idempotency_key({"a": 1, "b": 2})
    assert len(ids.idempotency_key(payload)) == 64


def test_logger_emits_json(capsys: pytest.CaptureFixture[str]) -> None:
    log = get_logger("test-json-logger-xyz")
    bind(log, logging.INFO, "hello", key="k1")
    line = capsys.readouterr().out.strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["msg"] == "hello"
    assert payload["key"] == "k1"
    assert payload["level"] == "INFO"
