"""Deterministic idempotency keys: same payload -> same key, always."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


def idempotency_key(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()
