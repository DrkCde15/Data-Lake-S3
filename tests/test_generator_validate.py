import io

import pandas as pd

from de_common.errors import ValidationError
from lake.generator import COLUMNS, GenConfig, generate, to_csv
from lake.validate import validate_transactions


def test_generate_is_deterministic() -> None:
    a = generate(GenConfig(n=100, seed=7))
    b = generate(GenConfig(n=100, seed=7))
    assert a == b
    assert generate(GenConfig(n=100, seed=8)) != a


def test_generate_schema_and_csv_roundtrip() -> None:
    rows = generate(GenConfig(n=50, seed=1))
    assert all(set(r) == set(COLUMNS) for r in rows)
    df = pd.read_csv(io.BytesIO(to_csv(rows)))
    assert list(df.columns) == COLUMNS
    assert len(df) == 50


def test_validate_accepts_clean() -> None:
    df = pd.read_csv(io.BytesIO(to_csv(generate(GenConfig(n=100, seed=3)))))
    out = validate_transactions(df)
    assert len(out) == 100


def test_validate_rejects_all_issue_classes() -> None:
    df = pd.read_csv(io.BytesIO(to_csv(generate(GenConfig(n=50, seed=3, inject_invalid=True)))))
    try:
        validate_transactions(df)
    except ValidationError as exc:
        msg = str(exc)
        assert "duplicate" in msg and "amount <= 0" in msg
        assert "unknown countries" in msg and "unparseable ts" in msg
    else:
        raise AssertionError("expected ValidationError")
