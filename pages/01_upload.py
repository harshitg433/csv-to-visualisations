import streamlit as st
import pandas as pd

from utils.loader import load_all_files, validate_all
from utils.schema import build_schema, detect_foreign_keys
from utils.db import get_connection, load_dataframes_to_sqlite, sanitize_dataframes

st.set_page_config(page_title="Upload Files", page_icon="📁", layout="wide")
st.title("📁 Upload Files")

# --- Guard: check session state is initialized ---
if "upload_complete" not in st.session_state:
    st.warning("Please start from the home page to initialize the app.")
    st.stop()

st.write("Upload CSV, Excel (.xlsx/.xls), or TSV files. Each file becomes a separate database table.")

# --- File uploader ---
uploaded_files = st.file_uploader(
    "Choose files",
    type=["csv", "tsv", "xlsx", "xls"],
    accept_multiple_files=True,
)

if not uploaded_files:
    st.info("Upload one or more files to continue.")

    if st.session_state.get("upload_complete"):
        st.divider()
        st.success("Previously uploaded files are still loaded.")
        dfs = st.session_state["uploaded_dataframes"]
        for table_name, df in dfs.items():
            with st.expander(f"**{table_name}** — {df.shape[0]:,} rows × {df.shape[1]} columns"):
                st.dataframe(df.head(10), use_container_width=True)
        st.page_link("pages/02_schema.py", label="→ Continue to Schema Review", icon="🗂️")
    st.stop()

# --- Load files on upload ---
with st.spinner("Loading files..."):
    dataframes, load_errors = load_all_files(uploaded_files)

if load_errors:
    st.error("Some files could not be loaded:")
    for err in load_errors:
        st.write(f"- **{err['file']}**: {err['error']}")

if not dataframes:
    st.error("No files were loaded successfully.")
    st.stop()

# --- Show summary ---
st.subheader(f"Loaded {len(dataframes)} table(s)")
for table_name, df in dataframes.items():
    with st.expander(f"**{table_name}** — {df.shape[0]:,} rows × {df.shape[1]} columns", expanded=True):
        col1, col2, col3 = st.columns(3)
        col1.metric("Rows", f"{df.shape[0]:,}")
        col2.metric("Columns", df.shape[1])
        col3.metric("Memory", f"{df.memory_usage(deep=True).sum() / 1024:.1f} KB")

        st.dataframe(df.head(10), use_container_width=True)

        # Column types summary
        dtype_summary = df.dtypes.reset_index()
        dtype_summary.columns = ["Column", "Type"]
        dtype_summary["Nulls"] = df.isna().sum().values
        dtype_summary["Null %"] = (df.isna().mean() * 100).round(1).astype(str) + "%"
        st.dataframe(dtype_summary, use_container_width=True, hide_index=True)

# --- Validation ---
st.subheader("Validation")
issues = validate_all(dataframes)
if issues:
    st.warning(f"Found {len(issues)} validation issue(s):")
    issues_df = pd.DataFrame(issues)
    st.dataframe(issues_df, use_container_width=True, hide_index=True)
else:
    st.success("No validation issues found.")

# --- Confirm button ---
st.divider()
if st.button("✅ Confirm & Load to Database", type="primary"):
    with st.spinner("Building schema and loading to SQLite..."):
        # Sanitize column names FIRST so schema, SQLite, and LLM all agree
        dataframes = sanitize_dataframes(dataframes)

        # Build schema
        raw_schema = build_schema(dataframes)
        raw_schema = detect_foreign_keys(dataframes, raw_schema)

        # Load to SQLite
        conn = get_connection()
        load_dataframes_to_sqlite(dataframes, conn)

        # Store in session state
        st.session_state["uploaded_dataframes"] = dataframes
        st.session_state["validation_issues"] = issues
        st.session_state["upload_complete"] = True
        st.session_state["raw_schema"] = raw_schema
        # Reset downstream state
        st.session_state["confirmed_schema"] = {}
        st.session_state["schema_ddl"] = ""
        st.session_state["schema_confirmed"] = False
        st.session_state["last_question"] = ""
        st.session_state["last_generated_sql"] = ""
        st.session_state["last_query_result"] = None
        st.session_state["viz_specs"] = []
        st.session_state["viz_figures"] = []
        st.session_state["dashboard_data"] = {}
        st.session_state["dashboard_figures"] = []

    st.success(f"Loaded {len(dataframes)} table(s) into database.")
    st.page_link("pages/02_schema.py", label="→ Continue to Schema Review", icon="🗂️")
