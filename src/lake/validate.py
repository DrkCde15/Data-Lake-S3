"""Validation for transaction records. Collects ALL issues, then fails fast."""

from __future__ import annotations

import re

import pandas as pd

from de_common.errors import ValidationError

from .generator import COLUMNS

KNOWN_COUNTRIES = {"BR", "US", "AR", "CL", "PT"}
KNOWN_STATUS = {"approved", "refunded"}


def validate_transactions(df: pd.DataFrame) -> pd.DataFrame:
    issues: list[str] = []

    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        issues.append(f"missing columns: {missing}")

    if issues:
        raise ValidationError("; ".join(issues))

    df = df.copy()
    df.columns = [c.strip() for c in df.columns]
    for col in ("transaction_id", "user_id", "merchant", "country", "currency", "status"):
        df[col] = df[col].astype(str).str.strip()

    # SCHEMA-01: normalize BEFORE checking, so "br" is fixed instead of
    # rejected; unexpected columns fail loudly instead of drifting silently.
    df["country"] = df["country"].str.upper()
    df["currency"] = df["currency"].str.upper()
    unexpected = [c for c in df.columns if c not in COLUMNS]
    if unexpected:
        issues.append(f"unexpected columns: {unexpected}")

    if df["transaction_id"].isna().any() or (df["transaction_id"] == "").any():
        issues.append("null/empty transaction_id found")
    dupes = int(df["transaction_id"].duplicated(keep=False).sum())
    if dupes:
        issues.append(f"duplicate transaction_id rows: {dupes}")

    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    if df["amount"].isna().any():
        issues.append("non-numeric amount found")
    if (df["amount"] <= 0).any():
        issues.append("amount <= 0 found")

    unknown_countries = sorted(set(df["country"]) - KNOWN_COUNTRIES)
    if unknown_countries:
        issues.append(f"unknown countries: {unknown_countries}")
    # Currency has an open domain (any ISO-4217 code), so only the shape is
    # checked: 3 uppercase letters. Closed sets would false-reject legit codes.
    bad_currency = sorted({c for c in set(df["currency"]) if not re.fullmatch(r"[A-Z]{3}", str(c))})
    if bad_currency:
        issues.append(f"unknown currencies: {bad_currency}")
    unknown_status = sorted(set(df["status"]) - KNOWN_STATUS)
    if unknown_status:
        issues.append(f"unknown status: {unknown_status}")

    # TIME-01: parse as UTC so a missing offset fails instead of silently
    # shifting the daily grain downstream.
    parsed = pd.to_datetime(df["ts"], utc=True, errors="coerce")
    if parsed.isna().any():
        issues.append("unparseable ts found")

    if issues:
        raise ValidationError("; ".join(issues))

    return df
