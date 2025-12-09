"""Data loading utilities for Contracts and Prices.

These functions are thin wrappers around pandas, but centralize
schema expectations and small normalizations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

import pandas as pd

from mtm_core.utils import logger


PathLike = Union[str, Path]


def _read_table(path: PathLike) -> pd.DataFrame:
    """Read a table from Excel or CSV based on file suffix."""

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if path.suffix.lower() in {".csv"}:
        return pd.read_csv(path)

    raise ValueError(f"Unsupported file type for {path}")


def load_contracts(path: PathLike) -> pd.DataFrame:
    """Load contracts from Excel/CSV into a DataFrame.

    The loader itself does minimal work; most validation is done later
    in the pipeline. However, it does log basic metadata.
    """

    logger.info("Loading contracts from %s", path)
    df = _read_table(path)
    logger.info("Loaded %d contract rows", len(df))
    return df


def load_prices(path: PathLike) -> pd.DataFrame:
    """Load prices from Excel/CSV into a DataFrame.

    Expects at least columns: ``Index``, ``Date``, ``Price`` and
    optionally ``Tenor``.
    """

    logger.info("Loading prices from %s", path)
    df = _read_table(path)

    required = ["Index", "Date", "Price"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Prices file missing required columns: {missing}")

    logger.info("Loaded %d price rows", len(df))
    return df
