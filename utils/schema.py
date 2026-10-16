from __future__ import annotations

import re
from typing import Any, Optional
from typing_extensions import TypedDict

import pandas as pd


# ---------------------------------------------------------------------------
# TypedDicts
# ---------------------------------------------------------------------------

class ColumnDef(TypedDict):
    name: str
    dtype: str          # pandas dtype string
    sample_values: list
    nullable: bool
    is_primary_key: bool


class FKRelationship(TypedDict):
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    confidence: float


class TableSchema(TypedDict):
    table_name: str
    columns: list[ColumnDef]
    primary_key: Optional[str]
    foreign_keys: list[FKRelationship]
    row_count: int


class VizSpec(TypedDict):
    chart_type: str     # bar | line | scatter | pie | histogram | heatmap | area | box
    title: str
    x_column: str
    y_column: str
    color_column: Optional[str]
    description: str


# ---------------------------------------------------------------------------
# Schema building
# ---------------------------------------------------------------------------

def _infer_dtype_label(series: pd.Series) -> str:
    """Return a human-readable dtype label."""
    dtype = series.dtype
    if pd.api.types.is_integer_dtype(dtype):
        return "integer"
    if pd.api.types.is_float_dtype(dtype):
        return "float"
    if pd.api.types.is_bool_dtype(dtype):
        return "boolean"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "datetime"
    return "text"


def _detect_primary_key(df: pd.DataFrame) -> Optional[str]:
    """Return the column name most likely to be a PK, or None."""
    # Prefer columns named id, *_id at start
    candidates: list[str] = []
    for col in df.columns:
        lower = col.lower().strip()
        if lower in ("id",) or lower.endswith("_id") or lower.startswith("id_"):
            candidates.append(col)

    for col in candidates:
        if df[col].is_unique and df[col].notna().all():
            return col

    # Fallback: any unique non-null column
    for col in df.columns:
        if df[col].is_unique and df[col].notna().all():
            return col

    return None


def build_schema(dataframes: dict[str, pd.DataFrame]) -> dict[str, TableSchema]:
    """Build a schema dict from a mapping of table_name → DataFrame."""
    schema: dict[str, TableSchema] = {}
    for table_name, df in dataframes.items():
        columns: list[ColumnDef] = []
        for col in df.columns:
            series = df[col]
            sample = series.dropna().head(5).tolist()
            columns.append(
                ColumnDef(
                    name=col,
                    dtype=_infer_dtype_label(series),
                    sample_values=sample,
                    nullable=bool(series.isna().any()),
                    is_primary_key=False,
                )
            )

        pk = _detect_primary_key(df)
        if pk:
            for col_def in columns:
                if col_def["name"] == pk:
                    col_def["is_primary_key"] = True

        schema[table_name] = TableSchema(
            table_name=table_name,
            columns=columns,
            primary_key=pk,
            foreign_keys=[],
            row_count=len(df),
        )
    return schema


# ---------------------------------------------------------------------------
# Foreign key detection
# ---------------------------------------------------------------------------

def detect_foreign_keys(
    dataframes: dict[str, pd.DataFrame],
    schema: dict[str, TableSchema],
    threshold: float = 0.6,
    sample_cap: int = 10_000,
) -> dict[str, TableSchema]:
    """
    Detect FK relationships by value-overlap heuristic.
    Mutates and returns the schema dict with foreign_keys populated.
    """
    # Pre-compute frozensets of unique values per (table, column)
    value_sets: dict[tuple[str, str], frozenset] = {}
    for table_name, df in dataframes.items():
        for col in df.columns:
            sample = df[col].dropna()
            if len(sample) > sample_cap:
                sample = sample.sample(sample_cap, random_state=42)
            value_sets[(table_name, col)] = frozenset(sample.astype(str).unique())

    table_names = list(dataframes.keys())
    fk_results: dict[str, list[FKRelationship]] = {t: [] for t in table_names}

    for i, from_table in enumerate(table_names):
        from_schema = schema[from_table]
        pk_cols = {
            col_def["name"]
            for col_def in from_schema["columns"]
            if col_def["is_primary_key"]
        }

        for from_col_def in from_schema["columns"]:
            from_col = from_col_def["name"]
            if from_col in pk_cols:
                continue  # skip PK columns as FK sources

            from_set = value_sets.get((from_table, from_col), frozenset())
            if len(from_set) == 0:
                continue

            for to_table in table_names:
                if to_table == from_table:
                    continue
                to_schema = schema[to_table]
                for to_col_def in to_schema["columns"]:
                    if not to_col_def["is_primary_key"]:
                        continue
                    to_col = to_col_def["name"]
                    to_set = value_sets.get((to_table, to_col), frozenset())
                    if len(to_set) == 0:
                        continue

                    overlap = len(from_set & to_set) / len(from_set)
                    if overlap >= threshold:
                        fk_results[from_table].append(
                            FKRelationship(
                                from_table=from_table,
                                from_column=from_col,
                                to_table=to_table,
                                to_column=to_col,
                                confidence=round(overlap, 3),
                            )
                        )

    for table_name, fks in fk_results.items():
        schema[table_name]["foreign_keys"] = fks

    return schema


# ---------------------------------------------------------------------------
# DDL string builder
# ---------------------------------------------------------------------------

def schema_to_ddl_string(schema: dict[str, TableSchema]) -> str:
    """Return a human-readable DDL string for all tables (for LLM prompts)."""
    lines: list[str] = []
    for table_name, tschema in schema.items():
        lines.append(f"CREATE TABLE {table_name} (")
        col_lines: list[str] = []
        for col in tschema["columns"]:
            parts = [f"  {col['name']} {col['dtype'].upper()}"]
            if col["is_primary_key"]:
                parts.append("PRIMARY KEY")
            if not col["nullable"]:
                parts.append("NOT NULL")
            col_lines.append(" ".join(parts))
        # Add FK constraints
        for fk in tschema["foreign_keys"]:
            col_lines.append(
                f"  FOREIGN KEY ({fk['from_column']}) REFERENCES "
                f"{fk['to_table']}({fk['to_column']})"
            )
        lines.append(",\n".join(col_lines))
        lines.append(");\n")
    return "\n".join(lines)
