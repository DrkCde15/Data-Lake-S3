"""Silver contract (SILVER-01): duplicates are rejected in bronze validation,
so bronze_to_silver is a deterministic pass-through, not a dedupe step.

- Duplicates (even across two raw files of the same date) fail the batch.
- Silver output is byte-identical to the bronze input.
Runs on moto (no live S3 needed).
"""

import io

import pandas as pd
import pytest
from moto import mock_aws

from de_common.config import Settings
from de_common.errors import ValidationError
from lake.generator import GenConfig, generate, to_csv
from lake.lake import LakeManager, layer_key
from lake.pipeline import bronze_to_silver, raw_to_bronze, seed_raw

DATE = "2026-10-08"


@pytest.fixture(name="lake")
def _lake(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.delenv("AWS_ENDPOINT_URL", raising=False)
    settings = Settings(aws_region="us-east-1", endpoint_url=None, lake_bucket="silver-test")
    with mock_aws():
        mgr = LakeManager(settings)
        mgr.ensure_bucket()
        yield mgr


def test_duplicate_across_raw_files_fails_batch(lake: LakeManager) -> None:
    seed_raw(lake, DATE, 50, 7)
    # Second file, different seed except one replayed transaction_id.
    rows = generate(GenConfig(n=10, seed=8, date=DATE))
    first = generate(GenConfig(n=50, seed=7, date=DATE))[0]
    rows[0]["transaction_id"] = first["transaction_id"]
    key = layer_key("raw", DATE, "transactions-seed8.csv")
    lake.upload_bytes(key, to_csv(rows), {"rows": "10"})
    with pytest.raises(ValidationError, match="duplicate"):
        raw_to_bronze(lake, DATE)


def test_silver_is_passthrough_of_bronze(lake: LakeManager) -> None:
    seed_raw(lake, DATE, 100, 7)
    bronze_key = raw_to_bronze(lake, DATE)
    silver_key = bronze_to_silver(lake, DATE)
    bronze = pd.read_csv(io.BytesIO(lake.get_bytes(bronze_key)))
    silver = pd.read_csv(io.BytesIO(lake.get_bytes(silver_key)))
    pd.testing.assert_frame_equal(silver, bronze)
