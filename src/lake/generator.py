"""Synthetic financial-transaction generator.

Deterministic by seed so pipelines and tests are reproducible.
Set inject_invalid=True to produce rows the validator must reject
(used by tests, never by the default seed path).
"""

from __future__ import annotations

import csv
import io
import random
import uuid
from dataclasses import dataclass

COLUMNS = ["transaction_id", "user_id", "amount", "currency", "merchant", "country", "ts", "status"]

_MERCHANTS = ["amazon", "mercado-livre", "ifood", "uber", "netflix", "shopee", "apple", "steam"]
_COUNTRIES = ["BR", "BR", "BR", "BR", "US", "AR", "CL", "PT"]


@dataclass(frozen=True)
class GenConfig:
    n: int = 1_000
    seed: int = 42
    date: str = "2026-10-08"
    inject_invalid: bool = False


def generate(cfg: GenConfig) -> list[dict[str, str]]:
    rng = random.Random(cfg.seed)
    rows: list[dict[str, str]] = []
    for _ in range(cfg.n):
        tx_id = str(uuid.UUID(int=rng.getrandbits(128)))
        amount = round(rng.lognormvariate(4.5, 1.0), 2)
        rows.append(
            {
                "transaction_id": tx_id,
                "user_id": f"user-{rng.randint(1, 200):04d}",
                "amount": f"{amount:.2f}",
                "currency": "BRL",
                "merchant": rng.choice(_MERCHANTS),
                "country": rng.choice(_COUNTRIES),
                "ts": f"{cfg.date}T{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:00",
                "status": rng.choice(["approved", "approved", "approved", "refunded"]),
            }
        )
    if cfg.inject_invalid:
        rows.append(
            {
                "transaction_id": rows[0]["transaction_id"],  # duplicate
                "user_id": "user-0001",
                "amount": "-50.00",  # negative
                "currency": "BRL",
                "merchant": "fraud-shop",
                "country": "XX",  # unknown
                "ts": "not-a-date",
                "status": "approved",
            }
        )
    return rows


def to_csv(rows: list[dict[str, str]]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")
