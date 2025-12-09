"""Synthetic data generator for Contracts and Prices.

Goal: create a **useful** synthetic dataset that exercises:
- Multiple indices
- A wide range of tenors (past / near / future)
- Different units (WMT / DMT), moisture, Fe grades, discounts
- Price curves with multiple dates per tenor and fallback-friendly gaps

Outputs:
- `data/Contracts_synthetic.xlsx`
- `data/Prices_synthetic.xlsx`
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd

from mtm_core.utils import logger, normalize_tenor_to_yyyymm

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"


def _load_or_create_base_contracts() -> pd.DataFrame:
    """Return a small, diverse base contracts table.

    If `data/Contracts.xlsx` exists, use it as a starting point.
    Otherwise, create a synthetic base with several indices and tenors.
    """

    contracts_path = DATA_DIR / "Contracts.xlsx"
    if contracts_path.exists():
        logger.info("Reading base Contracts from %s", contracts_path)
        base = pd.read_excel(contracts_path)
    else:
        logger.info("Base Contracts.xlsx not found; creating synthetic base contracts")
        base = pd.DataFrame(
            {
                "ContractID": ["C1", "C2", "C3", "C4"],
                "BaseIndex": ["PlattsIO62", "PlattsIO62", "TSI58", "MB65"],
                "Tenor": ["2024-06", "2024-12", "2025-06", "2026-01"],
                "Quantity": [100000, 80000, 120000, 60000],
                "Unit": ["WMT", "DMT", "WMT", "DMT"],
                "Moisture": [0.08, 0.0, 0.10, 0.0],
                "TypicalFe": [62, 65, "NoAdj", 64],
                "Cost": [5.0, 4.5, 6.0, 7.0],
                "Discount": [0.98, 1.0, 0.95, 1.02],
            }
        )

    return base


def _load_or_create_base_prices() -> pd.DataFrame:
    """Return a base prices table covering several months per index."""

    prices_path = DATA_DIR / "Prices.xlsx"
    if prices_path.exists():
        logger.info("Reading base Prices from %s", prices_path)
        base = pd.read_excel(prices_path)
        # Ensure we have the expected columns
        cols = ["Index", "Date", "Tenor", "Price"]
        missing = [c for c in cols if c not in base.columns]
        if missing:
            raise ValueError(f"Prices.xlsx missing columns: {missing}")
        return base

    logger.info("Base Prices.xlsx not found; creating synthetic base prices")
    # Create monthly prices over a 2‑year window for a few indices
    start = datetime(2024, 1, 1)
    months = pd.date_range(start, periods=24, freq="MS")
    indices = ["PlattsIO62", "TSI58", "MB65"]

    rows = []
    rng = np.random.default_rng(7)
    for idx in indices:
        # Set a base level per index
        if idx == "PlattsIO62":
            level = 120.0
        elif idx == "TSI58":
            level = 95.0
        else:
            level = 140.0

        for dt in months:
            tenor = f"{dt.year:04d}-{dt.month:02d}"
            price = level * rng.uniform(0.9, 1.1)
            rows.append({"Index": idx, "Date": dt, "Tenor": tenor, "Price": price})

    return pd.DataFrame(rows)


def _mutate_contracts(base: pd.DataFrame, num_copies: int = 4) -> pd.DataFrame:
    """Generate many contracts by mutating base rows across tenors and attributes."""

    rng = np.random.default_rng(42)
    rows = []

    # Define tenor shifts (months) to create past / near / future coverage
    tenor_shifts = [-12, -6, -3, 0, 3, 6, 12]

    for _, row in base.iterrows():
        base_tenor = normalize_tenor_to_yyyymm(row.get("Tenor"))
        if base_tenor is None:
            continue
        year, month = map(int, base_tenor.split("-"))

        for shift in tenor_shifts:
            # Compute shifted tenor
            new_month_index = (month - 1 + shift)  # can be negative
            new_year = year + new_month_index // 12
            new_month = new_month_index % 12 + 1
            shifted_tenor = f"{new_year:04d}-{new_month:02d}"

            for i in range(num_copies):
                new = row.copy()
                new["ContractID"] = f"{row['ContractID']}_T{shift:+d}_v{i+1}"
                new["Tenor"] = shifted_tenor

                # Vary quantity ±30%
                factor = rng.uniform(0.7, 1.3)
                new["Quantity"] = float(row["Quantity"]) * factor

                # Alternate units to ensure mix of WMT / DMT
                new["Unit"] = rng.choice(["WMT", "DMT"])

                # Random moisture (if WMT)
                if new["Unit"] == "WMT":
                    new["Moisture"] = rng.uniform(0.05, 0.12)
                else:
                    new["Moisture"] = 0.0

                # Occasionally set TypicalFe to NoAdj or missing
                choice = rng.choice(["orig", "NoAdj", "missing"])
                if choice == "NoAdj":
                    new["TypicalFe"] = "NoAdj"
                elif choice == "missing":
                    new["TypicalFe"] = None

                # Vary cost and discount slightly around base
                new["Cost"] = float(row["Cost"]) * rng.uniform(0.9, 1.1)
                new["Discount"] = float(row["Discount"]) * rng.uniform(0.95, 1.05)

                rows.append(new)

    return pd.DataFrame(rows)


def _expand_prices(base: pd.DataFrame) -> pd.DataFrame:
    """Expand base prices into a richer curve.

    For each (Index, Tenor) we create several price dates within the month,
    plus some neighbouring months and deliberate duplicates.
    """

    rng = np.random.default_rng(123)
    rows = []

    for _, row in base.iterrows():
        index = row["Index"]
        base_date = pd.to_datetime(row["Date"]).date()
        tenor_norm = normalize_tenor_to_yyyymm(row.get("Tenor", base_date))
        if tenor_norm is None:
            tenor_norm = f"{base_date.year:04d}-{base_date.month:02d}"

        year, month = map(int, tenor_norm.split("-"))

        # Within‑month prices on 5th, 15th, 25th
        for day in [5, 15, 25]:
            dt = datetime(year, month, day)
            price = float(row["Price"]) * rng.uniform(0.98, 1.02)
            rows.append(
                {
                    "Index": index,
                    "Date": dt,
                    "Tenor": tenor_norm,
                    "Price": price,
                }
            )

        # Nearby months for fallback logic: -6, -3, +3, +6
        for month_shift in [-6, -3, 3, 6]:
            new_month_index = (month - 1 + month_shift)
            shifted_year = year + new_month_index // 12
            shifted_month = new_month_index % 12 + 1
            tenor = f"{shifted_year:04d}-{shifted_month:02d}"
            dt = datetime(shifted_year, shifted_month, 15)
            base_price = float(row["Price"]) * rng.uniform(0.9, 1.1)

            # 1–2 duplicates per (Index, Tenor, Date)
            for _ in range(rng.integers(1, 3)):
                rows.append(
                    {
                        "Index": index,
                        "Date": dt,
                        "Tenor": tenor,
                        "Price": base_price + rng.uniform(-1.0, 1.0),
                    }
                )

    return pd.DataFrame(rows)


def generate() -> Tuple[Path, Path]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    base_contracts = _load_or_create_base_contracts()
    base_prices = _load_or_create_base_prices()

    contracts_syn = _mutate_contracts(base_contracts, num_copies=3)
    prices_syn = _expand_prices(base_prices)

    contracts_out = DATA_DIR / "Contracts_synthetic.xlsx"
    prices_out = DATA_DIR / "Prices_synthetic.xlsx"

    logger.info("Writing synthetic contracts to %s", contracts_out)
    contracts_syn.to_excel(contracts_out, index=False)

    logger.info("Writing synthetic prices to %s", prices_out)
    prices_syn.to_excel(prices_out, index=False)

    return contracts_out, prices_out


if __name__ == "__main__":
    generate()
