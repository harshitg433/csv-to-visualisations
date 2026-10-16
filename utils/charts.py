from __future__ import annotations

import io
from typing import Optional

import matplotlib
matplotlib.use("Agg")  # Must be before any other matplotlib import

import matplotlib.pyplot as plt
import matplotlib.figure
import pandas as pd

from utils.schema import VizSpec


def render_chart(spec: VizSpec, df: pd.DataFrame) -> matplotlib.figure.Figure:
    """
    Dispatch to the appropriate chart renderer based on spec.chart_type.
    Always returns a Figure. Never calls plt.show().
    """
    chart_type = spec["chart_type"].lower()
    dispatch = {
        "bar": _render_bar,
        "line": _render_line,
        "scatter": _render_scatter,
        "pie": _render_pie,
        "histogram": _render_histogram,
        "heatmap": _render_heatmap,
        "area": _render_area,
        "box": _render_box,
    }
    renderer = dispatch.get(chart_type, _render_bar)
    return renderer(spec, df)


def fig_to_png_bytes(fig: matplotlib.figure.Figure) -> bytes:
    """Convert a matplotlib Figure to PNG bytes at 150 dpi."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    buf.seek(0)
    return buf.read()


# ---------------------------------------------------------------------------
# Internal renderers
# ---------------------------------------------------------------------------

def _safe_columns(spec: VizSpec, df: pd.DataFrame) -> tuple[Optional[str], Optional[str]]:
    """Return (x_col, y_col) only if they exist in df, else None."""
    x = spec["x_column"] if spec["x_column"] in df.columns else None
    y = spec["y_column"] if spec["y_column"] in df.columns else None
    return x, y


def _render_bar(spec: VizSpec, df: pd.DataFrame) -> matplotlib.figure.Figure:
    fig, ax = plt.subplots(figsize=(10, 6))
    x, y = _safe_columns(spec, df)

    if x and y:
        color_col = spec.get("color_column")
        if color_col and color_col in df.columns:
            for label, group in df.groupby(color_col):
                ax.bar(group[x].astype(str), group[y], label=str(label), alpha=0.8)
            ax.legend()
        else:
            # Aggregate if needed
            plot_df = df.groupby(x)[y].sum().reset_index()
            ax.bar(plot_df[x].astype(str), plot_df[y])
    else:
        ax.text(0.5, 0.5, "Missing columns", ha="center", va="center", transform=ax.transAxes)

    ax.set_title(spec["title"])
    if x:
        ax.set_xlabel(x)
    if y:
        ax.set_ylabel(y)
    plt.xticks(rotation=45, ha="right")
    fig.tight_layout()
    return fig


def _render_line(spec: VizSpec, df: pd.DataFrame) -> matplotlib.figure.Figure:
    fig, ax = plt.subplots(figsize=(10, 6))
    x, y = _safe_columns(spec, df)

    if x and y:
        color_col = spec.get("color_column")
        if color_col and color_col in df.columns:
            for label, group in df.groupby(color_col):
                ax.plot(group[x], group[y], label=str(label), marker="o", markersize=4)
            ax.legend()
        else:
            ax.plot(df[x], df[y], marker="o", markersize=4)
    else:
        ax.text(0.5, 0.5, "Missing columns", ha="center", va="center", transform=ax.transAxes)

    ax.set_title(spec["title"])
    if x:
        ax.set_xlabel(x)
    if y:
        ax.set_ylabel(y)
    plt.xticks(rotation=45, ha="right")
    fig.tight_layout()
    return fig


def _render_scatter(spec: VizSpec, df: pd.DataFrame) -> matplotlib.figure.Figure:
    fig, ax = plt.subplots(figsize=(10, 6))
    x, y = _safe_columns(spec, df)

    if x and y:
        color_col = spec.get("color_column")
        if color_col and color_col in df.columns:
            categories = df[color_col].unique()
            cmap = plt.cm.get_cmap("tab10", len(categories))
            for i, label in enumerate(categories):
                mask = df[color_col] == label
                ax.scatter(df.loc[mask, x], df.loc[mask, y], label=str(label), color=cmap(i), alpha=0.7)
            ax.legend()
        else:
            ax.scatter(df[x], df[y], alpha=0.7)
    else:
        ax.text(0.5, 0.5, "Missing columns", ha="center", va="center", transform=ax.transAxes)

    ax.set_title(spec["title"])
    if x:
        ax.set_xlabel(x)
    if y:
        ax.set_ylabel(y)
    fig.tight_layout()
    return fig


def _render_pie(spec: VizSpec, df: pd.DataFrame) -> matplotlib.figure.Figure:
    fig, ax = plt.subplots(figsize=(8, 8))
    x, y = _safe_columns(spec, df)

    if x and y:
        plot_df = df.groupby(x)[y].sum().reset_index()
        # Keep top 10 slices for readability
        plot_df = plot_df.nlargest(10, y)
        ax.pie(
            plot_df[y],
            labels=plot_df[x].astype(str),
            autopct="%1.1f%%",
            startangle=90,
        )
    elif x:
        counts = df[x].value_counts().head(10)
        ax.pie(counts.values, labels=counts.index.astype(str), autopct="%1.1f%%", startangle=90)
    else:
        ax.text(0.5, 0.5, "Missing columns", ha="center", va="center", transform=ax.transAxes)

    ax.set_title(spec["title"])
    fig.tight_layout()
    return fig


def _render_histogram(spec: VizSpec, df: pd.DataFrame) -> matplotlib.figure.Figure:
    fig, ax = plt.subplots(figsize=(10, 6))
    x, y = _safe_columns(spec, df)
    col = x or y  # histogram uses one column

    if col and pd.api.types.is_numeric_dtype(df[col]):
        ax.hist(df[col].dropna(), bins=30, edgecolor="white", linewidth=0.5)
    elif col:
        counts = df[col].value_counts().head(20)
        ax.bar(counts.index.astype(str), counts.values)
        plt.xticks(rotation=45, ha="right")
    else:
        ax.text(0.5, 0.5, "Missing columns", ha="center", va="center", transform=ax.transAxes)

    ax.set_title(spec["title"])
    if col:
        ax.set_xlabel(col)
    ax.set_ylabel("Count")
    fig.tight_layout()
    return fig


def _render_heatmap(spec: VizSpec, df: pd.DataFrame) -> matplotlib.figure.Figure:
    fig, ax = plt.subplots(figsize=(10, 8))

    # Use numeric columns only
    numeric_df = df.select_dtypes(include="number")
    if numeric_df.shape[1] < 2:
        ax.text(0.5, 0.5, "Not enough numeric columns for heatmap",
                ha="center", va="center", transform=ax.transAxes)
        ax.set_title(spec["title"])
        return fig

    corr = numeric_df.corr()
    im = ax.imshow(corr, cmap="coolwarm", vmin=-1, vmax=1, aspect="auto")
    fig.colorbar(im, ax=ax, shrink=0.8)

    ax.set_xticks(range(len(corr.columns)))
    ax.set_yticks(range(len(corr.columns)))
    ax.set_xticklabels(corr.columns, rotation=45, ha="right")
    ax.set_yticklabels(corr.columns)

    # Annotate cells
    for i in range(len(corr)):
        for j in range(len(corr.columns)):
            ax.text(j, i, f"{corr.iloc[i, j]:.2f}", ha="center", va="center", fontsize=8)

    ax.set_title(spec["title"])
    fig.tight_layout()
    return fig


def _render_area(spec: VizSpec, df: pd.DataFrame) -> matplotlib.figure.Figure:
    fig, ax = plt.subplots(figsize=(10, 6))
    x, y = _safe_columns(spec, df)

    if x and y:
        ax.fill_between(range(len(df)), df[y], alpha=0.4)
        ax.plot(range(len(df)), df[y])
        ax.set_xticks(range(0, len(df), max(1, len(df) // 10)))
        ax.set_xticklabels(df[x].astype(str).iloc[::max(1, len(df) // 10)], rotation=45, ha="right")
    else:
        ax.text(0.5, 0.5, "Missing columns", ha="center", va="center", transform=ax.transAxes)

    ax.set_title(spec["title"])
    if x:
        ax.set_xlabel(x)
    if y:
        ax.set_ylabel(y)
    fig.tight_layout()
    return fig


def _render_box(spec: VizSpec, df: pd.DataFrame) -> matplotlib.figure.Figure:
    fig, ax = plt.subplots(figsize=(10, 6))
    x, y = _safe_columns(spec, df)

    if y and pd.api.types.is_numeric_dtype(df[y]):
        if x and x in df.columns:
            groups = [group[y].dropna().values for _, group in df.groupby(x)]
            labels = [str(label) for label, _ in df.groupby(x)]
            ax.boxplot(groups, labels=labels)
            plt.xticks(rotation=45, ha="right")
        else:
            ax.boxplot(df[y].dropna().values)
            ax.set_xticklabels([y])
    elif x and pd.api.types.is_numeric_dtype(df[x]):
        ax.boxplot(df[x].dropna().values)
        ax.set_xticklabels([x])
    else:
        ax.text(0.5, 0.5, "No numeric column for box plot",
                ha="center", va="center", transform=ax.transAxes)

    ax.set_title(spec["title"])
    if y:
        ax.set_ylabel(y)
    fig.tight_layout()
    return fig
