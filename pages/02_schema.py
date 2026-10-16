import copy

import streamlit as st
import pandas as pd

from utils.schema import TableSchema, ColumnDef, FKRelationship, schema_to_ddl_string

st.set_page_config(page_title="Schema Review", page_icon="🗂️", layout="wide")
st.title("🗂️ Schema Review")

# --- Guards ---
if "upload_complete" not in st.session_state:
    st.warning("Please start from the home page.")
    st.stop()

if not st.session_state.get("upload_complete"):
    st.warning("Please upload files first.")
    st.page_link("pages/01_upload.py", label="→ Go to Upload", icon="📁")
    st.stop()

raw_schema: dict[str, TableSchema] = st.session_state["raw_schema"]
if not raw_schema:
    st.error("No schema found. Please re-upload files.")
    st.stop()

st.write("Review and edit the auto-detected schema. You can change data types, set primary keys, and manage foreign keys.")

# --- Work on a mutable copy ---
if not st.session_state.get("confirmed_schema"):
    working_schema = copy.deepcopy(raw_schema)
else:
    working_schema = copy.deepcopy(st.session_state["confirmed_schema"])

DTYPE_OPTIONS = ["text", "integer", "float", "boolean", "datetime"]

# --- Per-table editors ---
updated_schema = copy.deepcopy(working_schema)

for table_name, tschema in working_schema.items():
    with st.expander(
        f"**{table_name}** — {tschema['row_count']:,} rows, {len(tschema['columns'])} columns",
        expanded=True,
    ):
        st.write("**Columns**")

        # Build editable table
        col_data = []
        for col in tschema["columns"]:
            col_data.append({
                "Column": col["name"],
                "Type": col["dtype"],
                "Primary Key": col["is_primary_key"],
                "Nullable": col["nullable"],
            })
        col_df = pd.DataFrame(col_data)

        edited = st.data_editor(
            col_df,
            key=f"col_editor_{table_name}",
            column_config={
                "Column": st.column_config.TextColumn("Column", disabled=True),
                "Type": st.column_config.SelectboxColumn("Type", options=DTYPE_OPTIONS),
                "Primary Key": st.column_config.CheckboxColumn("Primary Key"),
                "Nullable": st.column_config.CheckboxColumn("Nullable"),
            },
            use_container_width=True,
            hide_index=True,
        )

        # Apply edits back to schema
        for i, col in enumerate(updated_schema[table_name]["columns"]):
            if i < len(edited):
                row = edited.iloc[i]
                col["dtype"] = row["Type"]
                col["is_primary_key"] = bool(row["Primary Key"])
                col["nullable"] = bool(row["Nullable"])

        # Update PK field on table schema
        pk_cols = [
            c["name"] for c in updated_schema[table_name]["columns"] if c["is_primary_key"]
        ]
        updated_schema[table_name]["primary_key"] = pk_cols[0] if pk_cols else None

        # --- Foreign Keys ---
        fks = tschema.get("foreign_keys", [])
        if fks:
            st.write("**Detected Foreign Keys**")
            fk_data = []
            for fk in fks:
                fk_data.append({
                    "From Column": fk["from_column"],
                    "→ Table": fk["to_table"],
                    "→ Column": fk["to_column"],
                    "Confidence": f"{fk['confidence']:.0%}",
                })
            st.dataframe(pd.DataFrame(fk_data), use_container_width=True, hide_index=True)

            # Allow disabling individual FKs
            remove_fks = st.multiselect(
                "Remove FK relationships",
                options=[f"{fk['from_column']} → {fk['to_table']}.{fk['to_column']}" for fk in fks],
                key=f"remove_fk_{table_name}",
            )
            if remove_fks:
                to_remove = set(remove_fks)
                updated_schema[table_name]["foreign_keys"] = [
                    fk for fk in fks
                    if f"{fk['from_column']} → {fk['to_table']}.{fk['to_column']}" not in to_remove
                ]

# --- DDL Preview ---
st.divider()
st.subheader("Schema DDL Preview")
preview_ddl = schema_to_ddl_string(updated_schema)
st.code(preview_ddl, language="sql")

# --- Confirm ---
if st.button("✅ Confirm Schema", type="primary"):
    ddl = schema_to_ddl_string(updated_schema)
    st.session_state["confirmed_schema"] = updated_schema
    st.session_state["schema_ddl"] = ddl
    st.session_state["schema_confirmed"] = True
    st.success("Schema confirmed!")
    st.page_link("pages/03_query.py", label="→ Continue to Query", icon="🔍")

elif st.session_state.get("schema_confirmed"):
    st.info("Schema already confirmed. You can re-confirm after edits.")
    st.page_link("pages/03_query.py", label="→ Continue to Query", icon="🔍")
