"""Medallion promotion: raw -> bronze -> silver -> gold.

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
# Gold schema version. v2 splits revenue by status: revenue sums only
# approved transactions; refunds go to refunded_amount; net_revenue is
# revenue minus refunded_amount. See GOLD-01 in docs/revisao-engenharia-dados.md.
VERSION = "2"


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


def bronze_to_silver(lake: LakeManager, date: str) -> str:
    # Pass-through determinístico, sem drop_duplicates: duplicatas são
    # barradas a montante (validate_transactions rejeita o lote inteiro),
    # então a bronze nunca contém dupes e dedupar aqui seria código morto
    # que sugere uma garantia que não existe. Contrato travado em
    # tests/test_silver_contract.py. Ver SILVER-01 em
    # docs/revisao-engenharia-dados.md.
    df = pd.read_csv(io.BytesIO(lake.get_bytes(layer_key("bronze", date, "validated.csv"))))
    dest = layer_key("silver", date, "deduped.csv")
    lake.upload_bytes(
        dest,
        df.to_csv(index=False).encode(),
        {"rows": str(len(df)), "dedupe": "enforced-in-bronze-validation"},
    )
    bind(log, logging.INFO, "silver written", dest=dest, rows=len(df))
    return dest


def silver_to_gold(lake: LakeManager, date: str) -> str:
    df = pd.read_csv(io.BytesIO(lake.get_bytes(layer_key("silver", date, "deduped.csv"))))
    df["day"] = pd.to_datetime(df["ts"]).dt.date.astype(str)
    is_approved = df["status"] == "approved"
    is_refunded = df["status"] == "refunded"
    df = df.assign(
        is_approved=is_approved.astype(int),
        is_refunded=is_refunded.astype(int),
        approved_amount=df["amount"].where(is_approved, 0.0),
        refunded_amount=df["amount"].where(is_refunded, 0.0),
    )
    gold = (
        df.groupby(["day", "country"], as_index=False)
        .agg(
            transactions=("transaction_id", "count"),
            approved_transactions=("is_approved", "sum"),
            revenue=("approved_amount", "sum"),
            refunds=("is_refunded", "sum"),
            refunded_amount=("refunded_amount", "sum"),
        )
        .assign(net_revenue=lambda g: g["revenue"] - g["refunded_amount"])
        .round({"revenue": 2, "refunded_amount": 2, "net_revenue": 2})
        .sort_values(["day", "country"])
        .reset_index(drop=True)
    )
    dest = layer_key("gold", date, "daily-revenue.csv")
    lake.upload_bytes(
        dest,
        gold.to_csv(index=False).encode(),
        {"rows": str(len(gold)), "pipeline-version": VERSION},
    )
    bind(log, logging.INFO, "gold written", dest=dest, rows=len(gold))
    return dest


def run(lake: LakeManager, date: str, n: int, seed: int) -> dict[str, str]:
    lake.ensure_bucket()
    raw_key = seed_raw(lake, date, n, seed)
    bronze = raw_to_bronze(lake, date)
    silver = bronze_to_silver(lake, date)
    gold = silver_to_gold(lake, date)
    bind(
        log,
        logging.INFO,
        "pipeline done",
        date=date,
        ingested_at=datetime.now(UTC).isoformat(),
    )
    return {"raw": raw_key, "bronze": bronze, "silver": silver, "gold": gold}
