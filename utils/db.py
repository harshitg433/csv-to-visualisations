from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st


def get_connection() -> sqlite3.Connection:
    """
    Return a live SQLite in-memory connection from session state.
    Creates a new one if missing or dead (liveness check via SELECT 1).
    """
    conn = st.session_state.get("db_connection")
    if conn is not None:
        try:
            conn.execute("SELECT 1")
            return conn
        except Exception:
            pass  # connection is dead, create a new one

    conn = sqlite3.connect(":memory:", check_same_thread=False)
    st.session_state["db_connection"] = conn
    return conn


def sanitize_dataframes(
    dataframes: dict[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    """
    Return new DataFrames with all column names sanitized (spaces → underscores).
    Call this once after loading files so schema, SQLite, and LLM all see the same names.
    """
    result = {}
    for table_name, df in dataframes.items():
        df = df.copy()
        df.columns = [_sanitize_name(col) for col in df.columns]
        result[table_name] = df
    return result


def load_dataframes_to_sqlite(
    dataframes: dict[str, pd.DataFrame],
    conn: sqlite3.Connection,
) -> None:
    """Load all DataFrames into SQLite, replacing existing tables.
    Expects column names are already sanitized via sanitize_dataframes()."""
    for table_name, df in dataframes.items():
        df.to_sql(table_name, conn, if_exists="replace", index=False)


def run_query(sql: str, conn: sqlite3.Connection) -> pd.DataFrame:
    """Execute a SQL SELECT query and return results as a DataFrame."""
    try:
        return pd.read_sql_query(sql, conn)
    except Exception as exc:
        raise RuntimeError(f"Query failed: {exc}") from exc


def _sanitize_name(name: str) -> str:
    """Replace whitespace and problematic characters with underscores."""
    import re
    return re.sub(r"[^\w]", "_", str(name)).strip("_") or "col"
