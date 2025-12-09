"""Core MTM calculation pipeline.

This module ties together contracts, prices, tenor logic, and
adjustments to produce a final MTM report DataFrame.
"""

from __future__ import annotations

from datetime import date
from typing import Tuple

import numpy as np
import pandas as pd

from mtm_core.adjustments import prepare_contracts
from mtm_core.tenor_logic import TenorContext, classify_tenor, select_price_for_contract
from mtm_core.utils import Config, add_note, logger


def preprocess_prices(prices: pd.DataFrame, config: Config) -> pd.DataFrame:
    """Preprocess prices, including duplicate handling.

    Deduplicates rows with the same (Index, Tenor, Date) using the
    configured strategy.
    """

    df = prices.copy()

    if "Tenor" not in df.columns:
        df["Tenor"] = np.nan

    group_cols = ["Index", "Tenor", "Date"]

    if config.duplicate_price_method == "mean":
        agg_df = (
            df.groupby(group_cols, as_index=False)
            .agg({"Price": "mean"})
            .rename(columns={"Price": "Price"})
        )
    elif config.duplicate_price_method == "last":
        # Keep the last row per group
        idx = df.groupby(group_cols).tail(1).index
        agg_df = df.loc[idx, group_cols + ["Price"]]
    else:
        raise ValueError(f"Unknown duplicate_price_method: {config.duplicate_price_method}")

    num_before = len(df)
    num_after = len(agg_df)
    if num_after < num_before:
        logger.info(
            "Deduplicated prices from %d to %d rows using method '%s'",
            num_before,
            num_after,
            config.duplicate_price_method,
        )

    return agg_df


def calculate_mtm(
    contracts_df: pd.DataFrame,
    prices_df: pd.DataFrame,
    valuation_date: date,
    config: Config,
) -> pd.DataFrame:
    """Run the full MTM pipeline and return a report DataFrame.

    The resulting DataFrame contains at least the columns requested
    by the specification and is suitable for direct export.
    """

    contracts_prepared = prepare_contracts(contracts_df, config)
    prices_prepared = preprocess_prices(prices_df, config)

    records = []

    for _, row in contracts_prepared.iterrows():
        notes = row.get("notes", "") or ""

        tenor_ctx: TenorContext | None = classify_tenor(row["tenor"], valuation_date)
        if tenor_ctx is None:
            notes = add_note(notes, "Could not normalize tenor")
            logger.warning("Contract %s has invalid tenor: %s", row.get("contract_id"), row["tenor"])
            price_used = np.nan
            price_date = None
            tenor_type = None
        else:
            price_row, price_notes = select_price_for_contract(
                prices_prepared,
                base_index=row["base_index"],
                tenor_ctx=tenor_ctx,
                valuation_date=valuation_date,
            )
            notes = add_note(notes, price_notes)
            if price_row is None:
                price_used = np.nan
                price_date = None
            else:
                price_used = float(price_row["Price"])
                price_date = price_row["Date"]
            tenor_type = tenor_ctx.tenor_type

        fe_ratio = float(row.get("fe_ratio", np.nan))
        cost = float(row.get("cost", np.nan))
        discount = float(row.get("discount", np.nan))
        dmt_qty = float(row.get("dmt_qty", np.nan))

        if np.isnan(price_used) or np.isnan(dmt_qty) or np.isnan(discount):
            mtm_value = np.nan
            notes = add_note(notes, "Missing price, quantity, or discount; MTM not computed")
        else:
            mtm_value = (price_used * fe_ratio + cost) * discount * dmt_qty

        record = {
            "contract_id": row.get("contract_id"),
            "base_index": row.get("base_index"),
            "tenor": row.get("tenor"),
            "tenor_type": tenor_type,
            "price_used_date": price_date,
            "price_used": price_used,
            "fe_ratio": fe_ratio,
            "unit": row.get("unit"),
            "moisture": row.get("moisture"),
            "dmt_qty": dmt_qty,
            "cost": cost,
            "discount": discount,
            "mtm_value": mtm_value,
            # Optional / placeholder fields
            "mtm_prev_value": np.nan,
            "mtm_change": np.nan,
            "notes": notes,
        }
        records.append(record)

    report = pd.DataFrame.from_records(records)
    return report
