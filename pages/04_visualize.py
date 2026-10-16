import streamlit as st
import pandas as pd

from utils.llm import recommend_visualizations
from utils.plotly_charts import render_plotly_chart, build_chart
from utils.schema import VizSpec
from utils.export import dataframe_to_csv_bytes

st.set_page_config(page_title="Visualize", page_icon="📈", layout="wide")
st.title("📈 Interactive Visualizations")

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
    st.warning("Please enter your API key in the sidebar.")
    st.stop()

schema_ddl = st.session_state["schema_ddl"]
model = st.session_state.get("model", "openai/gpt-oss-120b")
provider = st.session_state.get("provider", "Groq")
question = st.session_state.get("last_question", "")

all_cols = result_df.columns.tolist()
num_cols = result_df.select_dtypes(include="number").columns.tolist()
cat_cols = result_df.select_dtypes(exclude="number").columns.tolist()

CHART_TYPES = ["bar", "line", "scatter", "pie", "histogram", "area", "box", "heatmap"]

# =========================================================================
# TAB layout: AI Recommendations | Chart Builder | All Charts
# =========================================================================
tab_ai, tab_build, tab_all = st.tabs([
    "🤖 AI Recommendations",
    "🎨 Chart Builder",
    "📊 All Charts",
])

# =========================================================================
# TAB 1: AI Recommendations
# =========================================================================
with tab_ai:
    st.write(f"**Query:** *{question}* — {len(result_df):,} rows × {result_df.shape[1]} cols")

    def _df_info(df: pd.DataFrame) -> str:
        lines = [f"Shape: {df.shape[0]} rows x {df.shape[1]} columns",
                 f"Columns: {', '.join(df.columns.tolist())}"]
        for col in df.columns:
            sample = df[col].dropna().head(5).tolist()
            lines.append(f"  - {col} ({df[col].dtype}): sample={sample}")
        return "\n".join(lines)

    if st.button("🤖 Get AI Chart Recommendations", type="primary"):
        with st.spinner(f"Getting recommendations from {provider}..."):
            try:
                specs = recommend_visualizations(
                    question, _df_info(result_df), schema_ddl, api_key, model, provider
                )
                st.session_state["viz_specs"] = specs
                st.session_state["viz_figures"] = []
            except Exception as exc:
                st.error(f"LLM error: {exc}")
                st.stop()

    specs: list[VizSpec] = st.session_state.get("viz_specs", [])

    if not specs:
        st.info("Click the button above to get AI-powered chart recommendations.")
    else:
        st.success(f"{len(specs)} chart(s) recommended")

        # Render all AI charts
        for i, spec in enumerate(specs):
            st.divider()

            head_col, del_col = st.columns([8, 1])
            with head_col:
                st.subheader(spec["title"])
                if spec.get("description"):
                    st.caption(spec["description"])
            with del_col:
                if st.button("🗑", key=f"del_ai_{i}", help="Remove this chart"):
                    new_specs = [s for j, s in enumerate(specs) if j != i]
                    st.session_state["viz_specs"] = new_specs
                    st.rerun()

            try:
                fig = render_plotly_chart(spec, result_df)
                st.plotly_chart(fig, use_container_width=True, key=f"ai_chart_{i}")
            except Exception as exc:
                st.warning(f"Could not render: {exc}")

            # Spec details
            with st.expander("Chart details"):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Type", spec["chart_type"].upper())
                c2.metric("X", spec["x_column"])
                c3.metric("Y", spec["y_column"])
                c4.metric("Color", spec.get("color_column") or "—")

# =========================================================================
# TAB 2: Interactive Chart Builder (Power BI / Tableau style)
# =========================================================================
with tab_build:
    st.subheader("Build Your Own Chart")
    st.caption("Select columns and chart type — chart updates live.")

    # Controls row
    c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 2, 2])
    with c1:
        b_type = st.selectbox("Chart Type", CHART_TYPES, key="b_type")
    with c2:
        b_x = st.selectbox("X Axis", [""] + all_cols, key="b_x")
    with c3:
        b_y = st.selectbox("Y Axis", [""] + all_cols, key="b_y")
    with c4:
        b_color = st.selectbox("Color / Group", ["None"] + all_cols, key="b_color")
    with c5:
        b_title = st.text_input("Chart Title", value=f"{b_type.title()} Chart", key="b_title")

    color_col = b_color if b_color != "None" else None

    # Live chart
    if b_x or b_y:
        try:
            fig = build_chart(result_df, b_type, b_x, b_y, color_col, b_title)
            st.plotly_chart(fig, use_container_width=True, key="builder_chart")
        except Exception as exc:
            st.warning(f"Chart error: {exc}")
    else:
        st.info("Select at least one axis column to see a chart.")

    # Data preview with stats
    st.divider()
    with st.expander("📋 Data Preview & Stats", expanded=False):
        tab_prev, tab_stat = st.tabs(["Data", "Statistics"])
        with tab_prev:
            st.dataframe(result_df, use_container_width=True)
        with tab_stat:
            st.dataframe(result_df.describe(include="all").T, use_container_width=True)

    # Save to AI tab
    st.divider()
    if st.button("➕ Save to All Charts", type="secondary",
                 disabled=not (b_x or b_y)):
        new_spec = VizSpec(
            chart_type=b_type,
            title=b_title,
            x_column=b_x,
            y_column=b_y,
            color_column=color_col,
            description="Created in Chart Builder",
        )
        existing = st.session_state.get("viz_specs", [])
        existing.append(new_spec)
        st.session_state["viz_specs"] = existing
        st.success("Saved! View it in the 'All Charts' tab.")

# =========================================================================
# TAB 3: All Charts (grid view + export)
# =========================================================================
with tab_all:
    all_specs: list[VizSpec] = st.session_state.get("viz_specs", [])

    if not all_specs:
        st.info("No charts yet. Use the AI Recommendations or Chart Builder tabs.")
    else:
        st.write(f"**{len(all_specs)} chart(s)** — shown in 2-column grid")

        # 2-column grid
        for i in range(0, len(all_specs), 2):
            cols = st.columns(2)
            for j, col in enumerate(cols):
                idx = i + j
                if idx >= len(all_specs):
                    break
                spec = all_specs[idx]
                with col:
                    hd, rm = st.columns([5, 1])
                    with hd:
                        st.write(f"**{spec['title']}**")
                        st.caption(f"{spec['chart_type'].upper()} · X:{spec['x_column']} · Y:{spec['y_column']}")
                    with rm:
                        if st.button("🗑", key=f"del_all_{idx}"):
                            new_specs = [s for k, s in enumerate(all_specs) if k != idx]
                            st.session_state["viz_specs"] = new_specs
                            st.rerun()
                    try:
                        fig = render_plotly_chart(spec, result_df)
                        st.plotly_chart(fig, use_container_width=True, key=f"all_chart_{idx}")
                    except Exception as exc:
                        st.warning(f"Render failed: {exc}")

        # Export
        st.divider()
        st.subheader("Export")
        exp1, exp2 = st.columns(2)
        with exp1:
            csv_bytes = dataframe_to_csv_bytes(result_df)
            st.download_button(
                "⬇ Download Data (CSV)",
                data=csv_bytes,
                file_name="viz_data.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with exp2:
            st.info(
                "Each chart above has interactive controls — "
                "use the camera icon (📷) on any chart to download it as PNG.",
                icon="💡",
            )

st.divider()
st.page_link("pages/05_dashboard.py", label="→ Continue to Dashboard", icon="🎨")
