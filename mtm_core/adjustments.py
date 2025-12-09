"""Adjustment logic: Fe ratio, WMT→DMT, numeric validation.

This module houses transformation functions that operate row-wise or
column-wise on pandas DataFrames, but are written to be individually
unit-testable.
"""

from __future__ import annotations

from typing import Tuple

import numpy as np
import pandas as pd

from mtm_core.utils import Config, logger, safe_to_numeric, add_note


def compute_fe_ratio(typical_fe_value) -> float:
    """Compute Fe ratio from a ``TypicalFe`` value.

    Rules:
    - If "NoAdj" (case-insensitive) or blank/NaN → 1.0.
    - Else, interpret as percentage and divide by 62.
      e.g. 62 → 1.0, 65 → 65/62.
    - Non-numeric values are treated as 1.0 with a warning.
    """

    if typical_fe_value is None or (isinstance(typical_fe_value, float) and np.isnan(typical_fe_value)):
        return 1.0

    text = str(typical_fe_value).strip()
    if text == "" or text.lower() == "noadj":
        return 1.0

    # Strip non-numeric characters like "%"
    filtered = "".join(ch for ch in text if (ch.isdigit() or ch in ".-"))
    try:
        val = float(filtered)
        return val / 62.0
    except Exception:
        logger.warning("TypicalFe '%s' could not be parsed, defaulting Fe ratio to 1.0", text)
        return 1.0


def convert_wmt_to_dmt(quantity, moisture, default_moisture: float) -> Tuple[float, str]:
    """Convert WMT quantity to DMT using ``quantity * (1 - moisture)``.

    Returns (dmt_qty, notes).
    If moisture is missing, uses ``default_moisture`` and records a note.
    """

    note = ""
    if quantity is None or (isinstance(quantity, float) and np.isnan(quantity)):
        return np.nan, "Missing quantity"

    q = float(quantity)

    if moisture is None or (isinstance(moisture, float) and np.isnan(moisture)):
        m = float(default_moisture)
        note = add_note(note, f"Moisture missing; defaulted to {default_moisture:.2f}")
    else:
        m = float(moisture)

    return q * (1.0 - m), note


def prepare_contracts(df: pd.DataFrame, config: Config) -> pd.DataFrame:
    """Prepare and validate contracts DataFrame.

    - Ensures numeric fields are numeric.
    - Computes Fe ratio and DMT quantity.
    - Adds ``notes`` column accumulating warnings.
    - Leaves price selection-related fields for later stages.
    """

    contracts = df.copy()

    # Standardize column names (tolerate minor differences)
    rename_map = {
        "ContractID": "contract_id",
        "BaseIndex": "base_index",
        "Tenor": "tenor",
        "Quantity": "quantity",
        "Unit": "unit",
        "Moisture": "moisture",
        "TypicalFe": "typical_fe",
        "Cost": "cost",
        "Discount": "discount",
    }
    contracts = contracts.rename(columns=rename_map)

    required_cols = [
        "contract_id",
        "base_index",
        "tenor",
        "quantity",
        "unit",
        "cost",
        "discount",
    ]
    missing = [c for c in required_cols if c not in contracts.columns]
    if missing:
        raise ValueError(f"Contracts DataFrame missing required columns: {missing}")

    # Initialize notes
    if "notes" not in contracts.columns:
        contracts["notes"] = ""

    # Numeric conversions
    for col in ["quantity", "moisture", "cost", "discount"]:
        if col in contracts.columns:
            contracts[col] = safe_to_numeric(contracts[col], field_name=col)

    # Fe ratio
    contracts["fe_ratio"] = contracts.get("typical_fe", np.nan).apply(compute_fe_ratio)

    # Unit handling and DMT calculation
    dmt_list = []
    note_list = []

    for _, row in contracts.iterrows():
        unit = str(row.get("unit", "")).upper()
        notes = row.get("notes", "") or ""
        qty = row.get("quantity")
        moisture = row.get("moisture")

        if unit == "DMT":
            dmt = qty
        elif unit == "WMT":
            dmt, note = convert_wmt_to_dmt(qty, moisture, config.default_moisture)
            notes = add_note(notes, note)
        else:
            message = f"Unsupported unit '{unit}' for contract {row.get('contract_id')}"
            if config.invalid_unit_policy == "fail":
                raise ValueError(message)
            logger.warning(message)
            notes = add_note(notes, message)
            dmt = np.nan

        dmt_list.append(dmt)
        note_list.append(notes)

    contracts["dmt_qty"] = dmt_list
    contracts["notes"] = note_list

    # Discount validation
    neg_disc_mask = (contracts["discount"] <= 0) | contracts["discount"].isna()
    if neg_disc_mask.any():
        message = f"{int(neg_disc_mask.sum())} contracts have non-positive or missing discounts"
        if config.raise_on_negative_discount:
            raise ValueError(message)
        logger.warning(message)
        contracts.loc[neg_disc_mask, "notes"] = contracts.loc[neg_disc_mask, "notes"].apply(
            lambda n: add_note(n, "Non-positive or missing discount")
        )

    return contracts
