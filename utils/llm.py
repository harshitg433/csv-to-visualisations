from __future__ import annotations

import json
import re
from typing import Any, Optional

import pandas as pd

from utils.schema import VizSpec


# ---------------------------------------------------------------------------
# JSON / SQL parsing helpers
# ---------------------------------------------------------------------------

def _parse_json_from_response(text: str) -> Any:
    """
    3-tier fallback JSON parser:
    1. Direct parse
    2. Strip markdown fences then parse
    3. Slice from first { or [ to last } or ]
    """
    # Tier 1: direct
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Tier 2: strip ```json ... ``` or ``` ... ``` fences
    stripped = re.sub(r"```(?:json)?\s*", "", text).replace("```", "").strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # Tier 3: find first { or [ and last } or ]
    obj_start = text.find("{")
    arr_start = text.find("[")

    if obj_start == -1 and arr_start == -1:
        raise ValueError(f"No JSON object found in response:\n{text[:500]}")

    if obj_start == -1:
        start, end_char = arr_start, "]"
    elif arr_start == -1:
        start, end_char = obj_start, "}"
    else:
        start = min(obj_start, arr_start)
        end_char = "}" if start == obj_start else "]"

    end = text.rfind(end_char)
    if end == -1:
        raise ValueError(f"No closing {end_char!r} found in response:\n{text[:500]}")

    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"JSON parse failed after slicing: {exc}\nText: {text[start:end+1][:500]}"
        )


def _extract_sql_from_response(text: str) -> str:
    """Strip ```sql fences and return cleaned SQL string."""
    match = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text.strip()


# ---------------------------------------------------------------------------
# SQL validation
# ---------------------------------------------------------------------------

_BLOCKED_KEYWORDS = re.compile(
    r"\b(DROP|DELETE|INSERT|UPDATE|ALTER|CREATE|TRUNCATE|EXEC|PRAGMA|ATTACH)\b",
    re.IGNORECASE,
)


def validate_sql(sql: str) -> tuple[bool, str]:
    """Returns (is_valid, error_message)."""
    cleaned = sql.strip()
    if not cleaned.upper().startswith("SELECT"):
        return False, "SQL must start with SELECT"
    blocked = _BLOCKED_KEYWORDS.search(cleaned)
    if blocked:
        return False, f"SQL contains blocked keyword: {blocked.group()}"
    return True, ""


# ---------------------------------------------------------------------------
# Provider-aware chat completion
# ---------------------------------------------------------------------------

def _chat_completion(
    prompt: str,
    api_key: str,
    model: str,
    provider: str,
    max_tokens: int = 1024,
    temperature: float = 0.3,
) -> str:
    """
    Send a single-turn prompt to the selected provider and return the response text.
    Supported providers: "Groq", "OpenAI", "Anthropic"
    """
    messages = [{"role": "user", "content": prompt}]

    if provider == "Groq":
        from groq import Groq
        client = Groq(api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return resp.choices[0].message.content or ""

    if provider == "OpenAI":
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return resp.choices[0].message.content or ""

    if provider == "Anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=messages,
        )
        return resp.content[0].text if resp.content else ""

    raise ValueError(f"Unknown provider: {provider!r}. Choose Groq, OpenAI, or Anthropic.")


# ---------------------------------------------------------------------------
# LLM calls
# ---------------------------------------------------------------------------

def generate_sql(
    question: str,
    schema_ddl: str,
    api_key: str,
    model: str,
    provider: str = "Groq",
) -> str:
    """Generate a SQL SELECT query from a natural language question."""
    ddl = schema_ddl[:2000] if len(schema_ddl) > 2000 else schema_ddl

    prompt = f"""You are an expert SQL analyst. Given the database schema below, generate a single SQL SELECT query to answer the user's question.

SCHEMA:
{ddl}

QUESTION: {question}

Rules:
- Return ONLY the SQL query, no explanation
- Use only SELECT statements
- Do not use DROP, DELETE, INSERT, UPDATE, ALTER, CREATE, TRUNCATE
- Use table and column names exactly as defined in the schema

SQL:"""

    raw = _chat_completion(prompt, api_key, model, provider, max_tokens=512, temperature=0.1)
    return _extract_sql_from_response(raw)


def recommend_visualizations(
    question: str,
    result_df_info: str,
    schema_ddl: str,
    api_key: str,
    model: str,
    provider: str = "Groq",
) -> list[VizSpec]:
    """Ask the LLM to recommend visualizations. Returns a list of VizSpec dicts."""
    ddl = schema_ddl[:2000] if len(schema_ddl) > 2000 else schema_ddl

    prompt = f"""You are a data visualization expert. Given the query result info and schema below, recommend 2-4 charts to visualize the data.

SCHEMA:
{ddl}

QUERY RESULT INFO:
{result_df_info}

ORIGINAL QUESTION: {question}

Return a JSON array of visualization specs. Each spec must have these exact keys:
- chart_type: one of "bar", "line", "scatter", "pie", "histogram", "heatmap", "area", "box"
- title: descriptive chart title
- x_column: column name for x-axis (must exist in result)
- y_column: column name for y-axis (must exist in result, or same as x for histogram)
- color_column: column name for color grouping, or null
- description: one sentence describing what this chart shows

Return ONLY valid JSON array, no explanation.

Example:
[
  {{
    "chart_type": "bar",
    "title": "Sales by Region",
    "x_column": "region",
    "y_column": "total_sales",
    "color_column": null,
    "description": "Compares total sales across different regions."
  }}
]"""

    raw = _chat_completion(prompt, api_key, model, provider, max_tokens=1024)

    try:
        specs = _parse_json_from_response(raw)
    except ValueError:
        raise ValueError(f"Could not parse visualization specs from LLM response:\n{raw}")

    if not isinstance(specs, list):
        specs = [specs]

    valid_chart_types = {"bar", "line", "scatter", "pie", "histogram", "heatmap", "area", "box"}
    result: list[VizSpec] = []
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        chart_type = str(spec.get("chart_type", "bar")).lower()
        if chart_type not in valid_chart_types:
            chart_type = "bar"
        result.append(
            VizSpec(
                chart_type=chart_type,
                title=str(spec.get("title", "Chart")),
                x_column=str(spec.get("x_column", "")),
                y_column=str(spec.get("y_column", "")),
                color_column=spec.get("color_column") or None,
                description=str(spec.get("description", "")),
            )
        )
    return result


def generate_dashboard(
    question: str,
    result_df_info: str,
    schema_ddl: str,
    api_key: str,
    model: str,
    provider: str = "Groq",
) -> dict:
    """Generate full dashboard content. Returns a dict."""
    ddl = schema_ddl[:2000] if len(schema_ddl) > 2000 else schema_ddl

    prompt = f"""You are a senior business analyst. Based on the query result and schema below, generate a comprehensive dashboard report.

SCHEMA:
{ddl}

QUERY RESULT INFO:
{result_df_info}

ORIGINAL QUESTION: {question}

Return a JSON object with these exact keys:
- title: dashboard title string
- executive_summary: 2-3 sentence overview paragraph
- kpis: array of objects with keys "label" (string), "value" (string), "delta" (string or null)
- insights: array of 3-5 insight strings
- recommendations: array of 2-3 recommendation strings
- viz_specs: array of 2-4 chart specs, each with keys: chart_type, title, x_column, y_column, color_column, description
  (chart_type must be one of: bar, line, scatter, pie, histogram, heatmap, area, box)

Return ONLY valid JSON, no explanation."""

    raw = _chat_completion(prompt, api_key, model, provider, max_tokens=4096)

    try:
        data = _parse_json_from_response(raw)
    except ValueError:
        raise ValueError(f"Could not parse dashboard data from LLM response:\n{raw}")

    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object for dashboard, got: {type(data)}")

    data.setdefault("title", "Dashboard")
    data.setdefault("executive_summary", "")
    data.setdefault("kpis", [])
    data.setdefault("insights", [])
    data.setdefault("recommendations", [])
    data.setdefault("viz_specs", [])

    valid_chart_types = {"bar", "line", "scatter", "pie", "histogram", "heatmap", "area", "box"}
    clean_specs: list[VizSpec] = []
    for spec in data.get("viz_specs", []):
        if not isinstance(spec, dict):
            continue
        chart_type = str(spec.get("chart_type", "bar")).lower()
        if chart_type not in valid_chart_types:
            chart_type = "bar"
        clean_specs.append(
            VizSpec(
                chart_type=chart_type,
                title=str(spec.get("title", "Chart")),
                x_column=str(spec.get("x_column", "")),
                y_column=str(spec.get("y_column", "")),
                color_column=spec.get("color_column") or None,
                description=str(spec.get("description", "")),
            )
        )
    data["viz_specs"] = clean_specs
    return data
