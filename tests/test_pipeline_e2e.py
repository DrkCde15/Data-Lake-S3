"""E2E against a live S3-compatible store (MinIO locally and in CI).

Skipped when nothing listens on the endpoint (e.g. plain `pytest` without
the stack up). Honors AWS_ENDPOINT_URL so CI can point it at its service.
"""

import io
import os
import socket
import urllib.parse

import pandas as pd
import pytest

from de_common.config import Settings
from lake.lake import LakeManager
from lake.pipeline import run

ENDPOINT = os.environ.get("AWS_ENDPOINT_URL", "http://127.0.0.1:9000")


def _up() -> bool:
    parts = urllib.parse.urlparse(ENDPOINT)
    try:
        with socket.create_connection((parts.hostname or "127.0.0.1", parts.port or 80), timeout=2):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not _up(), reason="S3 compatível não está rodando")


@pytest.fixture(name="lake")
def _lake(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", os.environ.get("AWS_ACCESS_KEY_ID", "minioadmin"))
    monkeypatch.setenv(
        "AWS_SECRET_ACCESS_KEY", os.environ.get("AWS_SECRET_ACCESS_KEY", "minioadmin")
    )
    settings = Settings(aws_region="sa-east-1", endpoint_url=ENDPOINT, lake_bucket="e2e-lake-test")
    mgr = LakeManager(settings)
    mgr.ensure_bucket()
    return mgr


def test_pipeline_bronze_validates_and_reruns_identical(lake: LakeManager) -> None:
    out = run(lake, "2026-10-08", 500, 42)
    bronze = pd.read_csv(io.BytesIO(lake.get_bytes(out["bronze"])))
    assert len(bronze) == 500
    assert bronze["transaction_id"].is_unique
    # idempotency: rerun produces byte-identical bronze
    out2 = run(lake, "2026-10-08", 500, 42)
    assert lake.get_bytes(out2["bronze"]) == lake.get_bytes(out["bronze"])
