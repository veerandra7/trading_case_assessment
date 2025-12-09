## Iron Ore MTM Valuation Engine

This repository implements a modular Market-to-Market (MTM) valuation engine for iron ore contracts, exposed **only via a Streamlit app**. The core calculation is in a small `mtm_core/` package, and `app.py` is the single entry point you run.

The MTM formula implemented is:

\[ \text{MTM} = (\text{BaseIndexPrice} \times \text{FeRatio} + \text{Cost}) \times \text{Discount} \times \text{DMT Quantity} \]

### Repository layout

- **`mtm_core/utils.py`**: Shared utilities, configuration, logging helpers, tenor normalization.
- **`mtm_core/loaders.py`**: Load and validate Contracts and Prices from Excel/CSV.
- **`mtm_core/tenor_logic.py`**: Tenor normalization and tenor type classification.
- **`mtm_core/adjustments.py`**: Fe ratio calculation, WMT→DMT conversion, numeric validation.
- **`mtm_core/mtm_calculator.py`**: Core MTM valuation pipeline over pandas DataFrames.
- **`mtm_core/report_generator.py`**: Output of MTM report to CSV/XLSX.
- **`generate_synthetic_data.py`**: Synthetic Contracts and Prices generation.
- **`app.py`**: Streamlit UI around the core engine (main entry point).
- **`data/`**: Input templates and assessment document.
- **`output/`**: MTM reports created by the app (CSV/XLSX).

### Data assumptions

- **Contracts input** is expected to contain at least: `ContractID`, `BaseIndex`, `Tenor`, `Quantity`, `Unit`, `Moisture`, `TypicalFe`, `Cost`, `Discount`.
- **Prices input** is expected to contain at least: `Index`, `Date`, `Tenor`, `Price`.
- If `Contracts.xlsx` / `Prices.xlsx` are not present under `data/`, the synthetic generator creates base mock datasets instead.

All assumptions and any deviations from the original spreadsheets should be reviewed and adjusted in `generate_synthetic_data.py` and `mtm_core/loaders.py` for your specific environment.

### Design decisions (engine behavior)

- **Duplicate price rows** (same Index + Tenor + Date) are **averaged** to a single row. This is deterministic, simple, and reduces noise while still reflecting the central price level. The behavior is controlled via `Config.duplicate_price_method` ("mean" or "last") in `mtm_core/utils.py`.
- **Tenor normalization**: Tenors are normalized to `YYYY-MM` using `dateutil.parser` to handle formats like `2025-01-15`, `Jan-25`, etc. Missing or invalid tenors are logged and flagged in the `notes` column.
- **Tenor type classification** (past/current/future) is based on comparing the tenor month with the valuation date month.
- **Price selection**:
  - **Past tenor**: last available price within that tenor month.
  - **Current tenor**: latest available price on or before the valuation date within that tenor month.
  - **Future tenor**: if no exact tenor exists, use the nearest upcoming tenor month with data; if none exists, fall back to the latest prior tenor month. All fallbacks are logged and surfaced in the `notes` column.
- **Fe ratio**:
  - If `TypicalFe` is `"NoAdj"` or blank → Fe ratio = **1.0**.
  - Otherwise, Fe ratio = `TypicalFe / 62` (62% benchmark). Non-numeric values are handled robustly with logging and fallbacks.
- **WMT → DMT**:
  - If `Unit` is `WMT` (case-insensitive), then `DMT = Quantity * (1 - Moisture)`.
  - If moisture is missing, the default moisture is **0.0** (configurable) and a warning is added to `notes`.
- **Validation**:
  - Numeric fields are validated and cast with `pandas.to_numeric`.
  - Negative or zero discounts/costs are logged and flagged; policy is configurable (warn vs. error).
  - Contracts with units neither `WMT` nor `DMT` are flagged and, by default, **skipped** from MTM aggregation (configurable to `fail`).
- **Optional fields**: `mtm_prev_value` and `mtm_change` columns are present but default to `NaN` in the baseline implementation.

### How to set up and run (Streamlit only)

From the project root:

```bash
./run.sh
```

This will:

- Create `.venv` if it does not exist.
- Install dependencies from `requirements.txt`.
- Generate synthetic data files (`data/Contracts_synthetic.xlsx`, `data/Prices_synthetic.xlsx`).
- Launch the Streamlit app on port 8501.

You can also run the steps manually:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python generate_synthetic_data.py
streamlit run app.py --server.port 8501
```

### Streamlit app behavior

The app (`app.py`) provides:

- **File uploads** for Contracts and Prices.
- **Valuation date input** (YYYY-MM-DD).
- **Run MTM** button, which executes the same core engine as the CLI used to, but now only through the app.
- **Table preview** of the MTM report (with a visible `notes` column; rows with notes are highlighted).
- **Download buttons** for CSV and XLSX.
- **Summary KPI**: total portfolio MTM.

All core logic lives in `mtm_core/`, and the UI is a thin wrapper that simply wires inputs to outputs.

### Configuration and fallbacks

Key configuration knobs live in the `Config` class in `mtm_core/utils.py`, including:

- **`duplicate_price_method`**: `"mean"` (default) or `"last"`.
- **`invalid_unit_policy`**: `"skip"` (default) or `"fail"`.
- **`default_moisture`**: default moisture used when missing.
- **`raise_on_negative_discount`**: whether to raise or only warn.

These are instantiated inside the app when running MTM and can be easily extended if you want to expose switches in the UI.

### Suggested test scenarios with synthetic data

After running `python generate_synthetic_data.py`, you get `data/Contracts_synthetic.xlsx` and `data/Prices_synthetic.xlsx`. Use these in the app and try the following valuation dates:

- **Past-tenor focus (more past contracts)**  
  - **Valuation date**: `2024-03-15`  
  - **Expectation**: Most contract tenors (e.g. `2024-06`, `2024-12`, `2025-06`) are in the *future* relative to this date. The engine will classify many contracts as **future**, and use future-tenor pricing with fallback to nearest later tenor where needed. MTM values will reflect more forward-looking prices.

- **Mixed past/current/future (month with rich data)**  
  - **Valuation date**: `2025-06-20`  
  - **Expectation**:  
    - Contracts with tenor `2025-06` are **current**; for these, the engine will pick the **latest price on or before 2025‑06‑20** (from multiple dates in June).  
    - Contracts with tenors before June 2025 (e.g. `2024-12`, `2025-03`) are **past** and will use the **last available price within their tenor month**.  
    - Contracts with tenors after June 2025 (e.g. `2025-12`, `2026-01`) are **future** and will use either their exact tenor month or the nearest later tenor as a fallback.  
  - **What to look for**: Changing the valuation date within June (e.g. `2025-06-05` vs `2025-06-25`) will change the price used for current‑tenor contracts, because June has multiple price dates.

- **Far-future valuation (most contracts in the past)**  
  - **Valuation date**: `2026-12-15`  
  - **Expectation**: Almost all synthetic contract tenors (centered around 2024–2026) are **past**. The engine will treat them as **past tenors** and select the **last available price in each contract’s tenor month**, largely independent of the exact valuation day. MTM will be driven by the end-of-month prices per tenor.

If you run the app with the **same uploaded synthetic files** and change only the valuation date as above, you should see the MTM report and total portfolio MTM change in line with these expectations, especially between the “mixed” scenario around June 2025 and the far-past / far-future scenarios.
