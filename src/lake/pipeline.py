"""Landing zone: raw -> bronze (validated).

This project owns ingestion and validation only. Silver/gold curation lives
downstream (projects 03/04) — this module intentionally stops at bronze so
there is exactly one owner per layer.

Idempotency by construction: every stage rewrites deterministic outputs
(overwrite, never append). Re-running a date recomputes identical objects.
"""

from __future__ import annotations

import io
import logging
from datetime import UTC, datetime

import pandas as pd

from de_common.logging import bind, get_logger

from .generator import GenConfig, generate, to_csv
from .lake import LakeManager, layer_key
from .validate import validate_transactions

log = get_logger("lake.pipeline")


def seed_raw(lake: LakeManager, date: str, n: int, seed: int) -> str:
    rows = generate(GenConfig(n=n, seed=seed, date=date))
    key = layer_key("raw", date, f"transactions-seed{seed}.csv")
    lake.upload_bytes(
        key,
        to_csv(rows),
        {"rows": str(len(rows)), "generator": "synthetic-v1", "seed": str(seed)},
    )
    return key


def raw_to_bronze(lake: LakeManager, date: str) -> str:
    src_keys = lake.list_keys(f"raw/date={date}/")
    if not src_keys:
        raise FileNotFoundError(f"no raw objects for date={date}")
    frames = [pd.read_csv(io.BytesIO(lake.get_bytes(k))) for k in src_keys]
    bronze = validate_transactions(pd.concat(frames, ignore_index=True))
    dest = layer_key("bronze", date, "validated.csv")
    lake.upload_bytes(
        dest,
        bronze.to_csv(index=False).encode(),
        {"rows": str(len(bronze)), "sources": str(len(src_keys)), "status": "validated"},
    )
    bind(log, logging.INFO, "bronze written", dest=dest, rows=len(bronze))
    return dest


def run(lake: LakeManager, date: str, n: int, seed: int) -> dict[str, str]:
    lake.ensure_bucket()
    raw_key = seed_raw(lake, date, n, seed)
    bronze = raw_to_bronze(lake, date)
    bind(
        log,
        logging.INFO,
        "pipeline done",
        date=date,
        ingested_at=datetime.now(UTC).isoformat(),
    )
    return {"raw": raw_key, "bronze": bronze}
