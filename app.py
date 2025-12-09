"""Streamlit presentation app for the iron ore MTM engine.

This app is a thin UI layer around the core engine:
- Upload Contracts and Prices files
- Enter valuation date
- Run MTM
- Preview results and download CSV/XLSX
- Show total portfolio MTM and highlight rows with notes
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
from dateutil import parser as date_parser

from mtm_core.loaders import load_contracts, load_prices
from mtm_core.mtm_calculator import calculate_mtm
from mtm_core.report_generator import save_report
from mtm_core.utils import Config

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"


st.set_page_config(page_title="Iron Ore MTM Engine", layout="wide")

st.title("Iron Ore MTM Valuation Engine")
st.markdown(
    "This Streamlit app is a thin layer over the core MTM engine. "
    "Upload your Contracts and Prices files, choose a valuation date, and run MTM."
)


with st.sidebar:
    st.header("Inputs")

    contracts_file = st.file_uploader(
        "Contracts file (xlsx/csv)", type=["xlsx", "xls", "csv"], key="contracts_file"
    )
    prices_file = st.file_uploader(
        "Prices file (xlsx/csv)", type=["xlsx", "xls", "csv"], key="prices_file"
    )

    valuation_date_str = st.text_input("Valuation date (YYYY-MM-DD)", value=str(date.today()))

    run_button = st.button("Run MTM", type="primary")


def _load_df_from_upload(uploaded_file):
    if uploaded_file is None:
        return None
    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(uploaded_file)
    if suffix == ".csv":
        return pd.read_csv(uploaded_file)
    raise ValueError(f"Unsupported uploaded file type: {suffix}")


if run_button:
    try:
        val_date = date_parser.parse(valuation_date_str).date()
    except Exception:
        st.error("Could not parse valuation date. Please use YYYY-MM-DD.")
        st.stop()

    # Determine contracts/prices DataFrames (always require uploads)
    if contracts_file is None or prices_file is None:
        st.error("Please upload both Contracts and Prices files.")
        st.stop()
    contracts_df = _load_df_from_upload(contracts_file)
    prices_df = _load_df_from_upload(prices_file)
    source_desc = "uploaded files"

    st.info(f"Running MTM using {source_desc} for valuation date {val_date}…")

    cfg = Config()
    report_df = calculate_mtm(contracts_df, prices_df, val_date, cfg)

    # Persist a copy so downloads use consistent content
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    temp_out = OUTPUT_DIR / "app_run"
    save_report(report_df, temp_out)

    total_mtm = report_df["mtm_value"].sum(skipna=True)

    st.subheader("Summary")
    st.metric("Total portfolio MTM", f"{total_mtm:,.2f}")

    st.subheader("MTM report preview")

    # Highlight rows with notes
    def _highlight_notes(row):
        if isinstance(row.get("notes"), str) and row["notes"].strip():
            return ["background-color: #fff3cd" for _ in row]
        return ["" for _ in row]

    st.dataframe(
        report_df.style.apply(_highlight_notes, axis=1),
        use_container_width=True,
        height=500,
    )

    st.subheader("Download report")

    csv_path = temp_out / "mtm_report.csv"
    xlsx_path = temp_out / "mtm_report.xlsx"

    csv_bytes = csv_path.read_bytes()
    xlsx_bytes = xlsx_path.read_bytes()

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            label="Download CSV",
            data=csv_bytes,
            file_name="mtm_report.csv",
            mime="text/csv",
        )
    with col2:
        st.download_button(
            label="Download XLSX",
            data=xlsx_bytes,
            file_name="mtm_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

else:
    st.info("Configure inputs on the left and click **Run MTM** to generate a report.")
