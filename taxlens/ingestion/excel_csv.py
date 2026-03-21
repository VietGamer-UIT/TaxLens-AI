"""Excel / CSV general ledger and invoice tabular ingestion."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def load_general_ledger(path: Path | str) -> pd.DataFrame:
    """Load GL from .csv or .xlsx (first sheet)."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(p)
    if suffix in (".xlsx", ".xls"):
        return pd.read_excel(p)
    raise ValueError(f"Unsupported format: {suffix}")


def normalize_gl_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map common VN/EN column aliases to canonical names."""
    aliases = {
        "so_chung_tu": ["voucher_no", "doc_no", "sct"],
        "ngay": ["date", "posting_date"],
        "tk_no": ["debit_account", "tk_nợ"],
        "tk_co": ["credit_account", "tk_có"],
        "so_tien": ["amount", "amt", "số tiền"],
        "dien_giai": ["description", "memo"],
    }
    lower = {str(c).strip().lower(): c for c in df.columns}
    rename: dict[str, str] = {}
    for canon, alts in aliases.items():
        for a in alts:
            if a.lower() in lower:
                rename[lower[a.lower()]] = canon
                break
    return df.rename(columns=rename)


def ledger_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return df.to_dict(orient="records")
