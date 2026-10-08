"""E2E against LocalStack (skipped in CI without it)."""

import io
import socket

import pandas as pd
import pytest

from de_common.config import Settings
from lake.lake import LakeManager
from lake.pipeline import run

ENDPOINT = "http://127.0.0.1:4566"


def _up() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 4566), timeout=2):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not _up(), reason="LocalStack não está rodando")


@pytest.fixture(name="lake")
def _lake(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    settings = Settings(aws_region="sa-east-1", endpoint_url=ENDPOINT, lake_bucket="e2e-lake-test")
    mgr = LakeManager(settings)
    mgr.ensure_bucket()
    return mgr


def test_pipeline_gold_matches_recomputation(lake: LakeManager) -> None:
    # Consistency check against LocalStack. NOTE: this recomputes the expected
    # frame with the same rule as the implementation, so it cannot catch a
    # wrong rule by itself — the revenue specification lives in the literal
    # test_gold_revenue.py::test_silver_to_gold_separates_refunds (E2E-01).
    out = run(lake, "2026-10-08", 500, 42)
    gold = pd.read_csv(io.BytesIO(lake.get_bytes(out["gold"])))
    silver = pd.read_csv(io.BytesIO(lake.get_bytes(out["silver"])))
    silver["day"] = pd.to_datetime(silver["ts"]).dt.date.astype(str)
    is_approved = silver["status"] == "approved"
    is_refunded = silver["status"] == "refunded"
    silver = silver.assign(
        approved_amount=silver["amount"].where(is_approved, 0.0),
        refunded_amount=silver["amount"].where(is_refunded, 0.0),
    )
    expected = (
        silver.groupby(["day", "country"], as_index=False)
        .agg(
            transactions=("transaction_id", "count"),
            approved_transactions=("status", lambda s: (s == "approved").sum()),
            revenue=("approved_amount", "sum"),
            refunds=("status", lambda s: (s == "refunded").sum()),
            refunded_amount=("refunded_amount", "sum"),
        )
        .assign(net_revenue=lambda g: g["revenue"] - g["refunded_amount"])
        .round({"revenue": 2, "refunded_amount": 2, "net_revenue": 2})
        .sort_values(["day", "country"])
        .reset_index(drop=True)
    )
    pd.testing.assert_frame_equal(gold, expected)
    # idempotency: rerun produces identical gold
    out2 = run(lake, "2026-10-08", 500, 42)
    gold2 = pd.read_csv(io.BytesIO(lake.get_bytes(out2["gold"])))
    pd.testing.assert_frame_equal(gold, gold2)
