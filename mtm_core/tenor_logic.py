"""Tenor normalization and price selection logic.

Responsible for:
- Normalizing contract and price tenors to YYYY-MM
- Classifying tenor type (past/current/future)
- Selecting the appropriate price row for a contract
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional, Tuple

import pandas as pd

from mtm_core.utils import logger, normalize_tenor_to_yyyymm, to_date, add_note

TenorType = Literal["past", "current", "future"]


class TenorContext:
    """Simple container for tenor information (no decorators)."""

    def __init__(self, contract_tenor_norm: str, tenor_type: TenorType) -> None:
        self.contract_tenor_norm = contract_tenor_norm
        self.tenor_type = tenor_type


def classify_tenor(contract_tenor: str, valuation_date: date) -> Optional[TenorContext]:
    """Classify a contract tenor as past/current/future relative to valuation date.

    Returns ``None`` if tenor cannot be normalized.
    """

    tenor_norm = normalize_tenor_to_yyyymm(contract_tenor)
    if tenor_norm is None:
        return None

    tenor_year, tenor_month = map(int, tenor_norm.split("-"))
    val_year, val_month = valuation_date.year, valuation_date.month

    if (tenor_year, tenor_month) < (val_year, val_month):
        ttype: TenorType = "past"
    elif (tenor_year, tenor_month) == (val_year, val_month):
        ttype = "current"
    else:
        ttype = "future"

    return TenorContext(contract_tenor_norm=tenor_norm, tenor_type=ttype)


def _prepare_prices(prices: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of prices with normalized tenor and date columns.

    Expected columns: ``Index``, ``Date``, optional ``Tenor``.
    """

    df = prices.copy()

    if "Date" not in df.columns:
        raise ValueError("Prices DataFrame must contain a 'Date' column")

    df["price_date"] = df["Date"].apply(to_date)
    if "Tenor" in df.columns:
        df["tenor_norm"] = df["Tenor"].apply(normalize_tenor_to_yyyymm)
    else:
        # Derive tenor from price date month
        df["tenor_norm"] = df["price_date"].apply(
            lambda d: f"{d.year:04d}-{d.month:02d}" if d is not None else None
        )

    return df


def select_price_for_contract(
    prices: pd.DataFrame,
    base_index: str,
    tenor_ctx: TenorContext,
    valuation_date: date,
) -> Tuple[Optional[pd.Series], str]:
    """Select the best price row for a contract and return (row, notes).

    Implements the business rules for past/current/future tenors and
    fallback to nearest later/prior tenor months.
    """

    prices_norm = _prepare_prices(prices)

    if "Index" not in prices_norm.columns:
        raise ValueError("Prices DataFrame must contain an 'Index' column")

    # Filter by index first
    idx_mask = prices_norm["Index"].astype(str) == str(base_index)
    subset = prices_norm[idx_mask].copy()
    if subset.empty:
        note = f"No prices found for index {base_index}"
        logger.warning(note)
        return None, note

    # Filter by tenor
    tenor = tenor_ctx.contract_tenor_norm

    same_tenor = subset[subset["tenor_norm"] == tenor]

    def _latest_within_month(df: pd.DataFrame) -> Optional[pd.Series]:
        df_valid = df.dropna(subset=["price_date"]).copy()
        if df_valid.empty:
            return None
        max_date = df_valid["price_date"].max()
        return df_valid[df_valid["price_date"] == max_date].iloc[0]

    notes = ""

    if tenor_ctx.tenor_type == "past":
        row = _latest_within_month(same_tenor)
        if row is None:
            notes = add_note(notes, "No price within past tenor month")
        else:
            return row, notes

    elif tenor_ctx.tenor_type == "current":
        df_valid = same_tenor.dropna(subset=["price_date"]).copy()
        df_valid = df_valid[df_valid["price_date"] <= valuation_date]
        if not df_valid.empty:
            max_date = df_valid["price_date"].max()
            row = df_valid[df_valid["price_date"] == max_date].iloc[0]
            return row, notes
        notes = add_note(notes, "No price on/before valuation date for current tenor")

    elif tenor_ctx.tenor_type == "future":
        row = _latest_within_month(same_tenor)
        if row is not None:
            return row, notes
        notes = add_note(notes, "No price for exact future tenor; applying fallback")

    # Fallback logic: nearest upcoming tenor with data, else latest prior tenor
    # First, build a list of distinct tenor months that have data for this index
    tenor_months = (
        subset.dropna(subset=["tenor_norm"])["tenor_norm"].astype(str).unique().tolist()
    )
    if not tenor_months:
        notes = add_note(notes, "No tenor months available for index")
        logger.warning(notes)
        return None, notes

    # Sort tenor months as (year, month)
    def _ym_key(t: str):
        y, m = t.split("-")
        return int(y), int(m)

    tenor_months_sorted = sorted(tenor_months, key=_ym_key)
    tenor_year, tenor_month = map(int, tenor.split("-"))

    later = [t for t in tenor_months_sorted if _ym_key(t) > (tenor_year, tenor_month)]
    prior = [t for t in tenor_months_sorted if _ym_key(t) < (tenor_year, tenor_month)]

    chosen_tenor = None
    if later:
        chosen_tenor = later[0]
        notes = add_note(notes, f"Used nearest later tenor {chosen_tenor} as fallback")
    elif prior:
        chosen_tenor = prior[-1]
        notes = add_note(notes, f"Used latest prior tenor {chosen_tenor} as fallback")
    else:
        notes = add_note(notes, "No alternative tenor available for fallback")
        logger.warning(notes)
        return None, notes

    subset_chosen = subset[subset["tenor_norm"] == chosen_tenor]
    row = _latest_within_month(subset_chosen)
    if row is None:
        notes = add_note(notes, f"No prices with dates for fallback tenor {chosen_tenor}")
        logger.warning(notes)
        return None, notes

    return row, notes
