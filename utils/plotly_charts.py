from __future__ import annotations

from typing import Optional
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.graph_objects import Figure

from utils.schema import VizSpec

# Shared color palette (Power BI / Tableau inspired)
COLOR_PALETTE = px.colors.qualitative.Set2
TEMPLATE = "plotly_dark"


def render_plotly_chart(spec: VizSpec, df: pd.DataFrame) -> Figure:
    """Dispatch to the right Plotly renderer based on spec.chart_type."""
    chart_type = spec["chart_type"].lower()
    dispatch = {
        "bar":       _bar,
        "line":      _line,
        "scatter":   _scatter,
        "pie":       _pie,
        "histogram": _histogram,
        "heatmap":   _heatmap,
        "area":      _area,
        "box":       _box,
    }
    renderer = dispatch.get(chart_type, _bar)
    fig = renderer(spec, df)
    fig.update_layout(
        template=TEMPLATE,
        title=dict(text=spec["title"], font=dict(size=16)),
        margin=dict(l=40, r=40, t=60, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def _col(spec: VizSpec, df: pd.DataFrame, key: str) -> Optional[str]:
    val = spec.get(key, "")
    return val if val and val in df.columns else None


def _bar(spec: VizSpec, df: pd.DataFrame) -> Figure:
    x, y = _col(spec, df, "x_column"), _col(spec, df, "y_column")
    color = _col(spec, df, "color_column")
    if not (x and y):
        return _empty(spec["title"])
    plot_df = df.groupby([x] + ([color] if color else []))[y].sum().reset_index()
    return px.bar(
        plot_df, x=x, y=y, color=color,
        color_discrete_sequence=COLOR_PALETTE,
        text_auto=True, barmode="group",
    )


def _line(spec: VizSpec, df: pd.DataFrame) -> Figure:
    x, y = _col(spec, df, "x_column"), _col(spec, df, "y_column")
    color = _col(spec, df, "color_column")
    if not (x and y):
        return _empty(spec["title"])
    return px.line(
        df, x=x, y=y, color=color,
        color_discrete_sequence=COLOR_PALETTE,
        markers=True,
    )


def _scatter(spec: VizSpec, df: pd.DataFrame) -> Figure:
    x, y = _col(spec, df, "x_column"), _col(spec, df, "y_column")
    color = _col(spec, df, "color_column")
    if not (x and y):
        return _empty(spec["title"])
    return px.scatter(
        df, x=x, y=y, color=color,
        color_discrete_sequence=COLOR_PALETTE,
        hover_data=df.columns.tolist(),
        trendline="ols" if pd.api.types.is_numeric_dtype(df[x]) else None,
    )


def _pie(spec: VizSpec, df: pd.DataFrame) -> Figure:
    x, y = _col(spec, df, "x_column"), _col(spec, df, "y_column")
    if x and y:
        plot_df = df.groupby(x)[y].sum().reset_index().nlargest(12, y)
        return px.pie(
            plot_df, names=x, values=y,
            color_discrete_sequence=COLOR_PALETTE,
            hole=0.35,
        )
    if x:
        counts = df[x].value_counts().head(12).reset_index()
        counts.columns = [x, "count"]
        return px.pie(counts, names=x, values="count",
                      color_discrete_sequence=COLOR_PALETTE, hole=0.35)
    return _empty(spec["title"])


def _histogram(spec: VizSpec, df: pd.DataFrame) -> Figure:
    col = _col(spec, df, "x_column") or _col(spec, df, "y_column")
    color = _col(spec, df, "color_column")
    if not col:
        return _empty(spec["title"])
    if pd.api.types.is_numeric_dtype(df[col]):
        return px.histogram(df, x=col, color=color,
                            color_discrete_sequence=COLOR_PALETTE,
                            nbins=30, marginal="box")
    counts = df[col].value_counts().head(20).reset_index()
    counts.columns = [col, "count"]
    return px.bar(counts, x=col, y="count",
                  color_discrete_sequence=COLOR_PALETTE, text_auto=True)


def _heatmap(spec: VizSpec, df: pd.DataFrame) -> Figure:
    num_df = df.select_dtypes(include="number")
    if num_df.shape[1] < 2:
        return _empty(spec["title"])
    corr = num_df.corr().round(2)
    return px.imshow(
        corr, text_auto=True, color_continuous_scale="RdBu_r",
        zmin=-1, zmax=1, aspect="auto",
    )


def _area(spec: VizSpec, df: pd.DataFrame) -> Figure:
    x, y = _col(spec, df, "x_column"), _col(spec, df, "y_column")
    color = _col(spec, df, "color_column")
    if not (x and y):
        return _empty(spec["title"])
    return px.area(
        df, x=x, y=y, color=color,
        color_discrete_sequence=COLOR_PALETTE,
    )


def _box(spec: VizSpec, df: pd.DataFrame) -> Figure:
    x, y = _col(spec, df, "x_column"), _col(spec, df, "y_column")
    color = _col(spec, df, "color_column")
    num_col = y if (y and pd.api.types.is_numeric_dtype(df[y])) else \
              x if (x and pd.api.types.is_numeric_dtype(df[x])) else None
    if not num_col:
        return _empty(spec["title"])
    cat_col = x if num_col == y else None
    return px.box(
        df, x=cat_col, y=num_col, color=color or cat_col,
        color_discrete_sequence=COLOR_PALETTE,
        points="outliers",
    )


def _empty(title: str) -> Figure:
    fig = go.Figure()
    fig.add_annotation(text="⚠ Column not found in result",
                       x=0.5, y=0.5, showarrow=False,
                       font=dict(size=14, color="gray"))
    return fig


# ---------------------------------------------------------------------------
# Quick-build chart from raw column selections (for the interactive builder)
# ---------------------------------------------------------------------------

def build_chart(
    df: pd.DataFrame,
    chart_type: str,
    x_col: str,
    y_col: str,
    color_col: Optional[str],
    title: str,
) -> Figure:
    """Build a Plotly chart directly from column selections."""
    from utils.schema import VizSpec
    spec = VizSpec(
        chart_type=chart_type,
        title=title,
        x_column=x_col,
        y_column=y_col,
        color_column=color_col or None,
        description="",
    )
    return render_plotly_chart(spec, df)
