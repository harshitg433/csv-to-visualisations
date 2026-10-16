from __future__ import annotations

import io
from typing import Any

import pandas as pd
import streamlit as st


SUPPORTED_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".xls"}


def load_file(uploaded_file: Any) -> pd.DataFrame:
    """
    Load an uploaded Streamlit file into a DataFrame.
    Supports CSV, TSV, XLSX, XLS. Only reads first sheet for Excel.
    """
    name: str = uploaded_file.name.lower()
    raw = uploaded_file.read()
    uploaded_file.seek(0)  # reset so callers can re-read if needed

    if name.endswith(".csv"):
        return pd.read_csv(io.BytesIO(raw))
    if name.endswith(".tsv"):
        return pd.read_csv(io.BytesIO(raw), sep="\t")
    if name.endswith(".xlsx") or name.endswith(".xls"):
        # Only first sheet — known limitation
        return pd.read_excel(io.BytesIO(raw), sheet_name=0)

    raise ValueError(f"Unsupported file type: {uploaded_file.name}")


def load_all_files(
    uploaded_files: list[Any],
) -> tuple[dict[str, pd.DataFrame], list[dict]]:
    """
    Load all uploaded files.
    Returns (dataframes_dict, errors_list).
    Table names are derived from filenames without extension.
    """
    dataframes: dict[str, pd.DataFrame] = {}
    errors: list[dict] = []

    for uf in uploaded_files:
        table_name = _filename_to_table_name(uf.name)
        try:
            df = load_file(uf)
            dataframes[table_name] = df
        except Exception as exc:
            errors.append({"file": uf.name, "error": str(exc)})

    return dataframes, errors


def validate_all(dataframes: dict[str, pd.DataFrame]) -> list[dict]:
    """
    Run basic validation on all DataFrames.
    Returns a list of issue dicts with keys: table, column, issue.
    """
    issues: list[dict] = []

    for table_name, df in dataframes.items():
        if df.empty:
            issues.append({"table": table_name, "column": None, "issue": "Table is empty"})
            continue

        for col in df.columns:
            null_pct = df[col].isna().mean()
            if null_pct == 1.0:
                issues.append(
                    {"table": table_name, "column": col, "issue": "Column is entirely null"}
                )
            elif null_pct > 0.5:
                issues.append(
                    {
                        "table": table_name,
                        "column": col,
                        "issue": f"Column has {null_pct:.0%} null values",
                    }
                )

        # Check for duplicate column names
        if len(df.columns) != len(set(df.columns)):
            issues.append(
                {"table": table_name, "column": None, "issue": "Duplicate column names detected"}
            )

    return issues


def _filename_to_table_name(filename: str) -> str:
    """Convert a filename to a valid SQL table name."""
    import re
    # Remove extension
    name = filename.rsplit(".", 1)[0]
    # Replace non-alphanumeric with underscore
    name = re.sub(r"[^\w]", "_", name)
    # Remove leading digits
    name = re.sub(r"^(\d)", r"t_\1", name)
    return name.lower() or "table"
