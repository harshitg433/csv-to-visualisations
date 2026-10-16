import streamlit as st
import pandas as pd

from utils.llm import generate_dashboard
from utils.plotly_charts import render_plotly_chart
from utils.export import dataframe_to_csv_bytes, figures_to_excel_bytes

st.set_page_config(page_title="Dashboard", page_icon="🎨", layout="wide")
st.title("🎨 Dashboard")

# --- Guards ---
if "upload_complete" not in st.session_state:
    st.warning("Please start from the home page.")
    st.stop()

if not st.session_state.get("schema_confirmed"):
    st.warning("Please complete schema review first.")
    st.page_link("pages/02_schema.py", label="→ Go to Schema Review", icon="🗂️")
    st.stop()

result_df: pd.DataFrame | None = st.session_state.get("last_query_result")
if result_df is None:
    st.warning("Please run a query first.")
    st.page_link("pages/03_query.py", label="→ Go to Query", icon="🔍")
    st.stop()

api_key = st.session_state.get("api_key", "")
if not api_key:
    st.warning("Please enter your API key in the sidebar (or set the env var).")
    st.stop()

schema_ddl = st.session_state["schema_ddl"]
model = st.session_state.get("model", "openai/gpt-oss-120b")
provider = st.session_state.get("provider", "Groq")
question = st.session_state.get("last_question", "")


def _build_df_info(df: pd.DataFrame) -> str:
    lines = [f"Shape: {df.shape[0]} rows x {df.shape[1]} columns"]
    lines.append(f"Columns: {', '.join(df.columns.tolist())}")
    for col in df.columns:
        dtype = str(df[col].dtype)
        sample = df[col].dropna().head(5).tolist()
        lines.append(f"  - {col} ({dtype}): sample={sample}")
    # Add basic stats for numeric columns
    num_cols = df.select_dtypes(include="number").columns.tolist()
    if num_cols:
        stats = df[num_cols].describe().to_string()
        lines.append(f"\nNumeric stats:\n{stats}")
    return "\n".join(lines)


# --- Generate dashboard button ---
if st.button("🤖 Generate Full Dashboard", type="primary"):
    result_info = _build_df_info(result_df)
    with st.spinner("Generating dashboard insights with Groq (this may take a moment)..."):
        try:
            dashboard_data = generate_dashboard(question, result_info, schema_ddl, api_key, model, provider)
            st.session_state["dashboard_data"] = dashboard_data
            st.session_state["dashboard_figures"] = []
        except Exception as exc:
            st.error(f"LLM error: {exc}")
            with st.expander("Error details"):
                import traceback
                st.code(traceback.format_exc())
            st.stop()

dashboard_data: dict = st.session_state.get("dashboard_data", {})

if not dashboard_data:
    st.info("Click 'Generate Full Dashboard' to create an AI-powered dashboard report.")
    st.stop()

# =========================================================================
# Dashboard Display
# =========================================================================

st.title(dashboard_data.get("title", "Dashboard"))
st.write(dashboard_data.get("executive_summary", ""))

# --- KPIs ---
kpis = dashboard_data.get("kpis", [])
if kpis:
    st.subheader("Key Performance Indicators")
    cols = st.columns(min(len(kpis), 4))
    for i, kpi in enumerate(kpis[:8]):
        with cols[i % 4]:
            delta = kpi.get("delta") or None
            st.metric(
                label=kpi.get("label", ""),
                value=kpi.get("value", ""),
                delta=delta,
            )

st.divider()

# --- Insights ---
insights = dashboard_data.get("insights", [])
if insights:
    st.subheader("Key Insights")
    for insight in insights:
        st.write(f"• {insight}")

# --- Recommendations ---
recommendations = dashboard_data.get("recommendations", [])
if recommendations:
    st.subheader("Recommendations")
    for rec in recommendations:
        st.write(f"→ {rec}")

st.divider()

# --- Charts (Plotly — interactive, no render button needed) ---
viz_specs = dashboard_data.get("viz_specs", [])

if viz_specs:
    st.subheader("Visualizations")
    for i in range(0, len(viz_specs), 2):
        cols = st.columns(2)
        for j, col in enumerate(cols):
            idx = i + j
            if idx >= len(viz_specs):
                break
            spec = viz_specs[idx]
            with col:
                st.write(f"**{spec['title']}**")
                st.caption(spec.get("description", ""))
                try:
                    fig = render_plotly_chart(spec, result_df)
                    st.plotly_chart(fig, use_container_width=True,
                                    key=f"dash_chart_{idx}")
                except Exception as exc:
                    st.warning(f"Chart failed: {exc}")

st.divider()

# --- Export ---
st.subheader("Export")

ecol1, ecol2 = st.columns(2)

with ecol1:
    csv_bytes = dataframe_to_csv_bytes(result_df)
    st.download_button(
        "⬇ Download Data (CSV)",
        data=csv_bytes,
        file_name="dashboard_data.csv",
        mime="text/csv",
        key="dl_csv_dashboard",
    )

with ecol2:
    dashboard_figures = st.session_state.get("dashboard_figures", [])
    if st.button("📊 Prepare Excel Export"):
        with st.spinner("Building Excel workbook..."):
            try:
                xlsx_bytes = figures_to_excel_bytes(
                    figures=[(t, f) for t, f in dashboard_figures if f is not None],
                    dashboard_data=dashboard_data,
                    result_df=result_df,
                )
                st.download_button(
                    "⬇ Download Dashboard (Excel)",
                    data=xlsx_bytes,
                    file_name="dashboard_report.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dl_xlsx_dashboard",
                )
            except Exception as exc:
                st.error(f"Excel export failed: {exc}")
