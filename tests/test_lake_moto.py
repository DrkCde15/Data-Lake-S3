"""Unit tests with moto (no LocalStack needed)."""

import pytest
from moto import mock_aws

from de_common.config import Settings
from lake.lake import LakeManager


@pytest.fixture(name="lake")
def _lake(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.delenv("AWS_ENDPOINT_URL", raising=False)
    settings = Settings(aws_region="us-east-1", endpoint_url=None, lake_bucket="test-bucket")
    with mock_aws():
        mgr = LakeManager(settings)
        mgr.ensure_bucket()
        yield mgr


def test_bucket_object_lifecycle(lake: LakeManager) -> None:
    lake.upload_bytes("raw/date=2026-10-08/a.csv", b"id\n1\n", {"rows": "1"})
    assert lake.exists("raw/date=2026-10-08/a.csv")
    assert not lake.exists("raw/date=2026-10-08/missing.csv")
    assert lake.list_keys("raw/") == ["raw/date=2026-10-08/a.csv"]
    assert lake.get_bytes("raw/date=2026-10-08/a.csv") == b"id\n1\n"
    lake.copy("raw/date=2026-10-08/a.csv", "bronze/date=2026-10-08/a.csv", {"status": "ok"})
    assert lake.exists("bronze/date=2026-10-08/a.csv")


def test_ensure_bucket_idempotent(lake: LakeManager) -> None:
    lake.ensure_bucket()
    lake.ensure_bucket()
