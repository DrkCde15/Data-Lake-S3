"""Gold revenue rule (GOLD-01): refunds must not inflate revenue.

Specification test with hand-crafted silver rows and a LITERAL expected
frame — deliberately not recomputed with the implementation's groupby, so a
regression in silver_to_gold fails here instead of mirroring the bug.
Runs on moto, so it executes in CI without LocalStack (covers E2E-01).
"""

import io

import pandas as pd
import pytest
from moto import mock_aws

from de_common.config import Settings
from lake.lake import LakeManager, layer_key
from lake.pipeline import run, silver_to_gold

DATE = "2026-10-08"

SILVER_CSV = """transaction_id,user_id,amount,currency,merchant,country,ts,status
t-001,user-0001,100.00,BRL,amazon,BR,2026-10-08T10:00:00,approved
t-002,user-0002,50.00,BRL,ifood,BR,2026-10-08T11:00:00,approved
t-003,user-0003,30.00,BRL,uber,BR,2026-10-08T12:00:00,refunded
t-004,user-0004,20.00,BRL,steam,US,2026-10-08T13:00:00,approved
"""


@pytest.fixture(name="lake")
def _lake(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.delenv("AWS_ENDPOINT_URL", raising=False)
    settings = Settings(aws_region="us-east-1", endpoint_url=None, lake_bucket="gold-test")
    with mock_aws():
        mgr = LakeManager(settings)
        mgr.ensure_bucket()
        yield mgr


def test_silver_to_gold_separates_refunds(lake: LakeManager) -> None:
    lake.upload_bytes(layer_key("silver", DATE, "deduped.csv"), SILVER_CSV.encode(), {"rows": "4"})
    dest = silver_to_gold(lake, DATE)
    assert dest == layer_key("gold", DATE, "daily-revenue.csv")

    gold = pd.read_csv(io.BytesIO(lake.get_bytes(dest)))
    expected = pd.DataFrame(
        [
            {
                "day": DATE,
                "country": "BR",
                "transactions": 3,
                "approved_transactions": 2,
                "revenue": 150.00,
                "refunds": 1,
                "refunded_amount": 30.00,
                "net_revenue": 120.00,
            },
            {
                "day": DATE,
                "country": "US",
                "transactions": 1,
                "approved_transactions": 1,
                "revenue": 20.00,
                "refunds": 0,
                "refunded_amount": 0.00,
                "net_revenue": 20.00,
            },
        ]
    )
    pd.testing.assert_frame_equal(gold, expected)


def test_full_run_gold_is_internally_consistent(lake: LakeManager) -> None:
    """Moto-backed end-to-end: runs raw->gold without LocalStack (CI-safe)."""
    out = run(lake, DATE, 200, 42)
    gold = pd.read_csv(io.BytesIO(lake.get_bytes(out["gold"])))
    silver = pd.read_csv(io.BytesIO(lake.get_bytes(out["silver"])))

    assert silver["status"].eq("refunded").sum() > 0  # fixture actually exercises refunds
    assert (gold["net_revenue"] == (gold["revenue"] - gold["refunded_amount"]).round(2)).all()
    assert (gold["transactions"] == gold["approved_transactions"] + gold["refunds"]).all()
    # revenue + refunded_amount must tie back to the silver total per group
    silver_total = silver.groupby(silver["ts"].str[:10] + "|" + silver["country"])["amount"].sum()
    gold_total = gold.set_index(gold["day"] + "|" + gold["country"]).apply(
        lambda r: r["revenue"] + r["refunded_amount"], axis=1
    )
    pd.testing.assert_series_equal(
        gold_total.sort_index(), silver_total.round(2).sort_index(), check_names=False
    )
