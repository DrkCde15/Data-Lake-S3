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


def test_generator_ts_is_explicit_utc() -> None:
    rows = generate(GenConfig(n=10, seed=3))
    assert all(r["ts"].endswith("+00:00") for r in rows)


def test_validate_normalizes_before_checking() -> None:
    rows = generate(GenConfig(n=20, seed=3))
    for r in rows:
        r["country"] = f" {r['country'].lower()} "
        r["currency"] = "brl"
    out = validate_transactions(pd.read_csv(io.BytesIO(to_csv(rows))))
    assert set(out["country"]) <= {"BR", "US", "AR", "CL", "PT"}
    assert set(out["currency"]) == {"BRL"}


def test_validate_rejects_unexpected_columns() -> None:
    df = pd.read_csv(io.BytesIO(to_csv(generate(GenConfig(n=10, seed=3)))))
    df["bonus_col"] = 1
    try:
        validate_transactions(df)
    except ValidationError as exc:
        assert "unexpected columns" in str(exc)
    else:
        raise AssertionError("expected ValidationError")


def test_validate_rejects_bad_currency() -> None:
    rows = generate(GenConfig(n=10, seed=3))
    rows[0]["currency"] = "XX"
    try:
        validate_transactions(pd.read_csv(io.BytesIO(to_csv(rows))))
    except ValidationError as exc:
        assert "unknown currencies" in str(exc)
    else:
        raise AssertionError("expected ValidationError")
