"""CLI: python -m lake.run --date 2026-10-08 --transactions 5000 --seed 42."""

from __future__ import annotations

import argparse
import logging
import sys

from de_common.config import Settings
from de_common.logging import bind, get_logger

from .lake import LakeManager
from .pipeline import run

log = get_logger("lake.cli")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="S3 medallion pipeline (local-first)")
    parser.add_argument("--date", required=True, help="partition date YYYY-MM-DD")
    parser.add_argument("--transactions", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    result = run(LakeManager(settings), args.date, args.transactions, args.seed)
    bind(log, logging.INFO, "done", **result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
