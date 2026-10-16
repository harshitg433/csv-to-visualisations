import streamlit as st
import pandas as pd

from utils.llm import generate_sql, validate_sql
from utils.db import get_connection, run_query

st.set_page_config(page_title="Query Data", page_icon="🔍", layout="wide")
st.title("🔍 Query Data")

# --- Guards ---
if "upload_complete" not in st.session_state:
    st.warning("Please start from the home page.")
    st.stop()

if not st.session_state.get("upload_complete"):
    st.warning("Please upload files first.")
    st.page_link("pages/01_upload.py", label="→ Go to Upload", icon="📁")
    st.stop()

if not st.session_state.get("schema_confirmed"):
    st.warning("Please confirm the schema first.")
    st.page_link("pages/02_schema.py", label="→ Go to Schema Review", icon="🗂️")
    st.stop()

api_key = st.session_state.get("api_key", "").strip()
provider = st.session_state.get("provider", "Groq")
model = st.session_state.get("model", "openai/gpt-oss-120b")

if not api_key:
    st.error(
        f"**No API key set for {provider}.**\n\n"
        "Open the sidebar and either:\n"
        "- Toggle off 'Use my own API key' (if the app has a default key), or\n"
        "- Paste your own API key into the text box."
    )
    st.stop()

# --- Show available tables ---
dfs = st.session_state.get("uploaded_dataframes", {})
with st.expander("Available tables", expanded=False):
    for table_name, df in dfs.items():
        st.write(f"**{table_name}**: {', '.join(df.columns.tolist())}")

# --- Previous result ---
if st.session_state.get("last_query_result") is not None:
    st.info(f"Last question: *{st.session_state['last_question']}*")

# --- Question input ---
st.subheader("Ask a Question")
question = st.text_area(
    "Natural language question",
    placeholder="e.g. Show me the top 10 customers by total sales",
    height=80,
    value=st.session_state.get("last_question", ""),
)

col1, col2 = st.columns([1, 4])
with col1:
    run_btn = st.button("🚀 Generate & Run", type="primary", disabled=not question.strip())
with col2:
    manual_sql_mode = st.checkbox("Edit SQL manually", value=False)

# --- SQL editor (manual mode) ---
manual_sql = ""
if manual_sql_mode and st.session_state.get("last_generated_sql"):
    manual_sql = st.text_area(
        "SQL Query",
        value=st.session_state["last_generated_sql"],
        height=120,
        key="manual_sql_input",
    )

# schema_ddl needed below
schema_ddl = st.session_state["schema_ddl"]

# --- Generate SQL ---
if run_btn and question.strip():
    with st.spinner(f"Generating SQL via {provider} ({model})..."):
        try:
            sql = generate_sql(question, schema_ddl, api_key, model, provider)
        except Exception as exc:
            import traceback
            st.error(f"**LLM error ({type(exc).__name__}):** {exc}")
            with st.expander("Full traceback"):
                st.code(traceback.format_exc())
            st.info(
                "**Common causes:**\n"
                "- Invalid or missing API key → check the sidebar\n"
                "- Network/firewall blocking the API endpoint\n"
                f"- Wrong model name for {provider}\n"
                "- Rate limit exceeded"
            )
            st.stop()

    st.session_state["last_question"] = question
    st.session_state["last_generated_sql"] = sql

    # Validate
    is_valid, err_msg = validate_sql(sql)
    if not is_valid:
        st.error(f"Generated SQL failed validation: {err_msg}")
        with st.expander("Raw SQL"):
            st.code(sql, language="sql")
        st.stop()

    # Execute
    conn = get_connection()
    try:
        with st.spinner("Running query..."):
            result_df = run_query(sql, conn)
        st.session_state["last_query_result"] = result_df
    except RuntimeError as exc:
        st.error(f"Query failed: {exc}")
        with st.expander("SQL that failed"):
            st.code(sql, language="sql")
        st.stop()

# --- Show generated SQL ---
if st.session_state.get("last_generated_sql"):
    st.subheader("Generated SQL")
    st.code(st.session_state["last_generated_sql"], language="sql")

# --- Manual SQL execution ---
if manual_sql_mode and manual_sql.strip():
    if st.button("▶ Run Manual SQL"):
        is_valid, err_msg = validate_sql(manual_sql)
        if not is_valid:
            st.error(f"SQL validation failed: {err_msg}")
        else:
            conn = get_connection()
            try:
                with st.spinner("Running query..."):
                    result_df = run_query(manual_sql, conn)
                st.session_state["last_query_result"] = result_df
                st.session_state["last_generated_sql"] = manual_sql
            except RuntimeError as exc:
                st.error(f"Query failed: {exc}")

# --- Show results ---
result_df = st.session_state.get("last_query_result")
if result_df is not None:
    st.subheader(f"Results — {len(result_df):,} rows × {result_df.shape[1]} columns")

    st.dataframe(result_df, use_container_width=True)

    # --- Export buttons ---
    from utils.export import dataframe_to_csv_bytes, dataframe_to_excel_bytes

    st.subheader("Export Results")

    col_csv, col_pbi, col_tab = st.columns(3)

    with col_csv:
        csv_bytes = dataframe_to_csv_bytes(result_df)
        st.download_button(
            "⬇ Download CSV",
            data=csv_bytes,
            file_name="query_result.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with col_pbi:
        xlsx_bytes = dataframe_to_excel_bytes(result_df)
        st.download_button(
            "📊 Export for Power BI (.xlsx)",
            data=xlsx_bytes,
            file_name="powerbi_data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    with col_tab:
        tab_csv_bytes = dataframe_to_csv_bytes(result_df)
        st.download_button(
            "📈 Export for Tableau (.csv)",
            data=tab_csv_bytes,
            file_name="tableau_data.csv",
            mime="text/csv",
            use_container_width=True,
        )

    # --- How-to guides ---
    with st.expander("📊 How to open in Power BI Desktop"):
        st.markdown("""
1. Open **Power BI Desktop** → click **Get Data** (Home ribbon)
2. Choose **Excel workbook** → select `powerbi_data.xlsx`
3. Check the table in the Navigator → click **Load**
4. Your data appears in the **Fields** panel — drag columns to build visuals
5. *(Optional)* Use **Transform Data** to rename columns or change types
        """)

    with st.expander("📈 How to open in Tableau Desktop / Tableau Public"):
        st.markdown("""
1. Open **Tableau** → under *Connect*, click **Text File**
2. Select `tableau_data.csv` → Tableau auto-detects column types
3. Drag the sheet to the canvas → click **Sheet 1** to start building
4. *(Tableau Public)* File → Save to Tableau Public to share online
        """)

    st.divider()
    st.page_link("pages/04_visualize.py", label="→ Visualize Results", icon="📈")
