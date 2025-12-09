"""Report generation helpers for MTM results."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from mtm_core.utils import logger


def save_report(report: pd.DataFrame, out_dir: str | Path) -> None:
    """Save the MTM report as CSV and XLSX under ``out_dir``.

    Filenames are ``mtm_report.csv`` and ``mtm_report.xlsx``.
    """

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    csv_path = out_path / "mtm_report.csv"
    xlsx_path = out_path / "mtm_report.xlsx"

    logger.info("Writing MTM report CSV to %s", csv_path)
    report.to_csv(csv_path, index=False)

    logger.info("Writing MTM report XLSX to %s", xlsx_path)
    report.to_excel(xlsx_path, index=False)
