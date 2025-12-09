"""Utility functions and configuration for the MTM engine.

This module centralizes configuration, logging, tenor normalization,

and general helpers to keep the rest of the engine focused on domain logic.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

from dateutil import parser as date_parser
import pandas as pd


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

LOGGER_NAME = "mtm_engine"
logger = logging.getLogger(LOGGER_NAME)

if not logger.handlers:
    # Simple console logger; can be overridden by caller.
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Configuration (kept simple – just a plain class)
# ---------------------------------------------------------------------------


class Config:
    """Simple configuration object for MTM behavior.

    Attributes have sensible defaults and can be overridden by passing
    keyword arguments to the constructor, e.g. ``Config(duplicate_price_method="last")``.
    """

    def __init__(
        self,
        duplicate_price_method: str = "mean",
        invalid_unit_policy: str = "skip",
        default_moisture: float = 0.0,
        raise_on_negative_discount: bool = False,
    ) -> None:
        # How to handle duplicate price rows for the same (Index, Tenor, Date)
        # - "mean": average
        # - "last": keep last in input order
        self.duplicate_price_method = duplicate_price_method

        # Policy for contracts with units not in {"WMT", "DMT"}
        # - "skip": skip contract and mark in notes
        # - "fail": raise an exception
        self.invalid_unit_policy = invalid_unit_policy

        # Default moisture to use when missing (for WMT → DMT conversion)
        self.default_moisture = default_moisture

        # Whether to raise on negative or zero discounts; if False, only warn
        self.raise_on_negative_discount = raise_on_negative_discount


# ---------------------------------------------------------------------------
# General helpers
# ---------------------------------------------------------------------------


def to_date(value) -> Optional[date]:
    """Best-effort conversion of a value to a ``datetime.date``.

    Returns ``None`` for blank/NaN.
    """

    if pd.isna(value) or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date_parser.parse(str(value)).date()
    except Exception:  # pragma: no cover - defensive
        logger.warning("Could not parse date value: %s", value)
        return None


def normalize_tenor_to_yyyymm(value) -> Optional[str]:
    """Normalize a tenor-like value to ``YYYY-MM``.

    Accepts strings like ``"2025-01-15"``, ``"Jan-25"``, ``"2025/01"``, etc.
    Returns ``None`` for invalid/blank values.
    """

    if pd.isna(value) or value == "":
        return None

    # If the value already looks like YYYY-MM, keep it.
    try:
        text = str(value).strip()
        if len(text) == 7 and text[4] == "-":
            # rudimentary check, e.g. "2025-01"
            return text
    except Exception:  # pragma: no cover - defensive
        pass

    try:
        dt = date_parser.parse(str(value), dayfirst=False, yearfirst=False)
        return f"{dt.year:04d}-{dt.month:02d}"
    except Exception:
        logger.warning("Could not normalize tenor value: %s", value)
        return None


def safe_to_numeric(series: pd.Series, field_name: str) -> pd.Series:
    """Convert a series to numeric with logging on failures.

    Invalid values become NaN but are logged.
    """

    numeric = pd.to_numeric(series, errors="coerce")
    num_invalid = numeric.isna() & ~series.isna()
    if num_invalid.any():
        logger.warning(
            "Field %s: %d values could not be converted to numeric and became NaN",
            field_name,
            int(num_invalid.sum()),
        )
    return numeric


def add_note(existing: str, new_note: str) -> str:
    """Concatenate notes in a stable, readable way."""

    if not existing:
        return new_note
    if not new_note:
        return existing
    return f"{existing} | {new_note}"
