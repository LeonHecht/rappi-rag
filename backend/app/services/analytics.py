from __future__ import annotations

from dataclasses import dataclass
from difflib import get_close_matches
from pathlib import Path
import re
from typing import Any

import duckdb
import pandas as pd
import yaml

from backend.app.core.config import settings


WEEK_RE = re.compile(r"^L([0-8])W(?:_(?:VALUE|ROLL))?$", re.IGNORECASE)
SAFE_TABLES = {"metrics_long", "orders_long"}
UNSAFE_SQL_RE = re.compile(
    r"\b(drop|delete|update|insert|alter|create|attach|copy|pragma|detach|vacuum|truncate|replace|merge|call|export|import|install|load|read_csv|read_parquet|read_json|from_csv_auto|parquet_scan|sqlite_scan)\b",
    re.IGNORECASE,
)
CSV_ENCODINGS = ("utf-8", "utf-8-sig", "cp1252", "latin1")


@dataclass(frozen=True)
class AnalyticsPaths:
    data_dir: Path
    db_path: Path
    metric_config_path: Path


def get_paths() -> AnalyticsPaths:
    return AnalyticsPaths(
        data_dir=Path(settings.ANALYTICS_DATA_DIR),
        db_path=Path(settings.ANALYTICS_DB_PATH),
        metric_config_path=Path(settings.ANALYTICS_METRIC_CONFIG),
    )


def _connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    paths = get_paths()
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(paths.db_path), read_only=read_only)


def _clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip().upper() for c in out.columns]
    return out


def _read_csv(csv_path: str | Path, **kwargs: Any) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in CSV_ENCODINGS:
        try:
            return pd.read_csv(csv_path, encoding=encoding, **kwargs)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ValueError(
        f"Could not decode CSV with supported encodings: {', '.join(CSV_ENCODINGS)}"
    ) from last_error


def _week_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if WEEK_RE.match(c)]


def _normalize_week(col: str) -> str:
    match = WEEK_RE.match(col)
    if not match:
        return col
    return f"L{match.group(1)}W"


def _to_float(series: pd.Series) -> pd.Series:
    if series.dtype == object:
        series = series.astype(str).str.replace("%", "", regex=False).str.replace(",", "", regex=False)
    return pd.to_numeric(series, errors="coerce")


def _detect_dataset(df: pd.DataFrame) -> str | None:
    columns = set(df.columns)
    week_cols = _week_columns(df)
    if {"COUNTRY", "CITY", "ZONE", "METRIC"}.issubset(columns) and week_cols:
        if any(c.endswith("_VALUE") for c in week_cols) or {"ZONE_TYPE", "ZONE_PRIORITIZATION"}.issubset(columns):
            return "metrics"
        return "orders"
    return None


def normalize_metrics_csv(csv_path: str | Path) -> pd.DataFrame:
    df = _clean_columns(_read_csv(csv_path))
    week_cols = _week_columns(df)
    id_cols = [c for c in ["COUNTRY", "CITY", "ZONE", "ZONE_TYPE", "ZONE_PRIORITIZATION", "METRIC"] if c in df.columns]
    long_df = df.melt(id_vars=id_cols, value_vars=week_cols, var_name="week", value_name="value")
    long_df["week"] = long_df["week"].map(_normalize_week)
    long_df["value"] = _to_float(long_df["value"])
    for col in ["ZONE_TYPE", "ZONE_PRIORITIZATION"]:
        if col not in long_df:
            long_df[col] = None
    return long_df.rename(
        columns={
            "COUNTRY": "country",
            "CITY": "city",
            "ZONE": "zone",
            "ZONE_TYPE": "zone_type",
            "ZONE_PRIORITIZATION": "zone_prioritization",
            "METRIC": "metric",
        }
    )[["country", "city", "zone", "zone_type", "zone_prioritization", "metric", "week", "value"]]


def normalize_orders_csv(csv_path: str | Path) -> pd.DataFrame:
    df = _clean_columns(_read_csv(csv_path))
    week_cols = _week_columns(df)
    id_cols = [c for c in ["COUNTRY", "CITY", "ZONE", "METRIC"] if c in df.columns]
    long_df = df.melt(id_vars=id_cols, value_vars=week_cols, var_name="week", value_name="orders")
    long_df["week"] = long_df["week"].map(_normalize_week)
    long_df["orders"] = _to_float(long_df["orders"])
    return long_df.rename(
        columns={"COUNTRY": "country", "CITY": "city", "ZONE": "zone", "METRIC": "metric"}
    )[["country", "city", "zone", "metric", "week", "orders"]]


def initialize_database() -> None:
    with _connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS metrics_long (
                country VARCHAR, city VARCHAR, zone VARCHAR, zone_type VARCHAR,
                zone_prioritization VARCHAR, metric VARCHAR, week VARCHAR, value DOUBLE
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS orders_long (
                country VARCHAR, city VARCHAR, zone VARCHAR, metric VARCHAR, week VARCHAR, orders DOUBLE
            )
            """
        )


def load_csv_to_duckdb(csv_path: str | Path, replace: bool = False) -> dict[str, Any]:
    csv_path = Path(csv_path)
    df = _clean_columns(_read_csv(csv_path, nrows=5))
    dataset = _detect_dataset(df)
    if dataset is None:
        return {"loaded": False, "reason": "CSV columns do not match a known analytics dataset."}

    normalized = normalize_metrics_csv(csv_path) if dataset == "metrics" else normalize_orders_csv(csv_path)
    table = "metrics_long" if dataset == "metrics" else "orders_long"
    initialize_database()
    with _connect() as con:
        if replace:
            con.execute(f"DELETE FROM {table}")
        con.register("incoming_csv", normalized)
        con.execute(f"INSERT INTO {table} SELECT * FROM incoming_csv")
        con.unregister("incoming_csv")
    return {"loaded": True, "dataset": dataset, "table": table, "rows": len(normalized), "db_path": str(get_paths().db_path)}


def load_csv_directory(input_dir: str | Path, replace: bool = True) -> list[dict[str, Any]]:
    initialize_database()
    results = []
    first_for_table: set[str] = set()
    for csv_path in sorted(Path(input_dir).glob("*.csv")):
        probe = _clean_columns(_read_csv(csv_path, nrows=5))
        dataset = _detect_dataset(probe)
        table = "metrics_long" if dataset == "metrics" else "orders_long" if dataset == "orders" else None
        results.append(load_csv_to_duckdb(csv_path, replace=replace and table not in first_for_table))
        if table:
            first_for_table.add(table)
    return results


def load_metric_dictionary() -> dict[str, str]:
    path = get_paths().metric_config_path
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("metrics", {}) or {}


def describe_schema() -> dict[str, Any]:
    initialize_database()
    metric_descriptions = load_metric_dictionary()
    with _connect(read_only=True) as con:
        tables = [r[0] for r in con.execute("SHOW TABLES").fetchall() if r[0] in SAFE_TABLES]
        columns = {
            table: [{"name": r[0], "type": r[1]} for r in con.execute(f"DESCRIBE {table}").fetchall()]
            for table in tables
        }

        def distinct(table: str, col: str) -> list[Any]:
            if table not in tables:
                return []
            return [r[0] for r in con.execute(f"SELECT DISTINCT {col} FROM {table} WHERE {col} IS NOT NULL ORDER BY {col}").fetchall()]

        metrics = sorted(set(distinct("metrics_long", "metric") + distinct("orders_long", "metric")))
        return {
            "tables": tables,
            "columns": columns,
            "metrics": metrics,
            "metric_descriptions": {m: metric_descriptions[m] for m in metrics if m in metric_descriptions},
            "countries": sorted(set(distinct("metrics_long", "country") + distinct("orders_long", "country"))),
            "cities": sorted(set(distinct("metrics_long", "city") + distinct("orders_long", "city"))),
            "zones": sorted(set(distinct("metrics_long", "zone") + distinct("orders_long", "zone"))),
            "zone_types": distinct("metrics_long", "zone_type"),
            "zone_prioritization_values": distinct("metrics_long", "zone_prioritization"),
            "weeks": sorted(set(distinct("metrics_long", "week") + distinct("orders_long", "week")), key=_week_sort_key),
        }


def _week_sort_key(week: str) -> int:
    match = re.match(r"L(\d+)W", str(week))
    return -int(match.group(1)) if match else 99


def preview_table(table: str, limit: int = 5) -> dict[str, Any]:
    if table not in SAFE_TABLES:
        return {"error": f"Unknown or unsafe table: {table}", "allowed_tables": sorted(SAFE_TABLES)}
    limit = max(1, min(int(limit or 5), 20))
    return run_sql(f"SELECT * FROM {table}", max_rows=limit)


def validate_metric_name(metric_phrase: str, limit: int = 5) -> dict[str, Any]:
    phrase = (metric_phrase or "").strip()
    metrics = describe_schema().get("metrics", [])
    if not phrase:
        return {"input": metric_phrase, "match": None, "candidates": metrics[:limit]}
    if phrase in metrics:
        return {"input": metric_phrase, "match": phrase, "candidates": [phrase], "method": "exact"}
    lowered = {m.lower(): m for m in metrics}
    if phrase.lower() in lowered:
        match = lowered[phrase.lower()]
        return {"input": metric_phrase, "match": match, "candidates": [match], "method": "case_insensitive"}
    candidates = get_close_matches(phrase.lower(), list(lowered.keys()), n=limit, cutoff=0.45)
    mapped = [lowered[c] for c in candidates]
    return {"input": metric_phrase, "match": mapped[0] if mapped else None, "candidates": mapped, "method": "fuzzy"}


def _validate_select_sql(sql: str) -> str | None:
    cleaned = (sql or "").strip().rstrip(";").strip()
    if not cleaned:
        return "SQL query is empty."
    if ";" in cleaned:
        return "Only one SELECT statement is allowed."
    if not re.match(r"^(select|with)\b", cleaned, re.IGNORECASE):
        return "Only SELECT queries are allowed."
    if UNSAFE_SQL_RE.search(cleaned):
        return "Unsafe SQL keyword detected. Only read-only SELECT analytics queries are allowed."
    return None


def run_sql(sql: str, max_rows: int | None = None) -> dict[str, Any]:
    initialize_database()
    max_rows = max(1, min(int(max_rows or settings.ANALYTICS_MAX_ROWS), settings.ANALYTICS_MAX_ROWS))
    error = _validate_select_sql(sql)
    if error:
        return {"error": error, "columns": [], "rows": [], "row_count": 0, "truncated": False}
    cleaned = sql.strip().rstrip(";").strip()
    limited_sql = f"SELECT * FROM ({cleaned}) AS analytics_query LIMIT {max_rows + 1}"
    try:
        with _connect(read_only=True) as con:
            result = con.execute(limited_sql)
            columns = [d[0] for d in result.description or []]
            rows = result.fetchall()
    except Exception as exc:
        return {"error": str(exc), "columns": [], "rows": [], "row_count": 0, "truncated": False}
    truncated = len(rows) > max_rows
    rows = rows[:max_rows]
    dict_rows = [dict(zip(columns, row)) for row in rows]
    return {
        "columns": columns,
        "rows": dict_rows,
        "row_count": len(dict_rows),
        "truncated": truncated,
        "summary": _numeric_summary(dict_rows, columns),
    }


def _numeric_summary(rows: list[dict[str, Any]], columns: list[str]) -> dict[str, dict[str, float]]:
    summary: dict[str, dict[str, float]] = {}
    if not rows:
        return summary
    frame = pd.DataFrame(rows)
    for col in columns:
        series = pd.to_numeric(frame[col], errors="coerce") if col in frame else pd.Series(dtype=float)
        series = series.dropna()
        if not series.empty:
            summary[col] = {"min": float(series.min()), "max": float(series.max()), "avg": float(series.mean())}
    return summary


def generate_chart(sql: str, chart_type: str = "bar", title: str | None = None, x: str | None = None, y: str | None = None) -> dict[str, Any]:
    result = run_sql(sql)
    if result.get("error"):
        return result
    rows = result.get("rows", [])
    columns = result.get("columns", [])
    if not rows or len(columns) < 2:
        return {"error": "Chart generation requires at least two result columns.", "result": result}
    x = x or columns[0]
    numeric_cols = [c for c in columns if c != x and c in _numeric_summary(rows, columns)]
    y = y or (numeric_cols[0] if numeric_cols else columns[1])
    plot_type = "scatter" if chart_type == "scatter" else "bar" if chart_type == "bar" else "scatter"
    mode = "markers" if chart_type == "scatter" else "lines+markers" if chart_type == "line" else None
    trace = {"type": plot_type, "x": [r.get(x) for r in rows], "y": [r.get(y) for r in rows], "name": y}
    if mode:
        trace["mode"] = mode
    return {"chart_type": chart_type, "spec": {"data": [trace], "layout": {"title": title or "", "xaxis": {"title": x}, "yaxis": {"title": y}}}, "source": result}


def generate_executive_report(threshold: float | None = None) -> str:
    threshold = float(threshold if threshold is not None else settings.ANALYTICS_ANOMALY_THRESHOLD)
    initialize_database()
    with _connect(read_only=True) as con:
        metrics_df = con.execute("SELECT * FROM metrics_long").fetchdf()
        orders_df = con.execute("SELECT * FROM orders_long").fetchdf()
    if metrics_df.empty and orders_df.empty:
        return _empty_report()
    anomalies = _find_anomalies(metrics_df, threshold)
    trends = _find_trends(metrics_df)
    benchmarks = _find_benchmarks(metrics_df)
    correlations = _find_correlations(metrics_df)
    opportunities = _find_opportunities(metrics_df, orders_df)
    top_findings = (anomalies[:2] + trends[:1] + benchmarks[:1] + opportunities[:1])[:5]
    return _format_report(top_findings, anomalies, trends, benchmarks, correlations, opportunities)


def _find_anomalies(df: pd.DataFrame, threshold: float) -> list[str]:
    findings = []
    if df.empty:
        return findings
    wide = df.pivot_table(index=["country", "city", "zone", "metric"], columns="week", values="value", aggfunc="mean")
    for idx, row in wide.iterrows():
        if "L1W" not in row or "L0W" not in row or pd.isna(row.get("L1W")) or pd.isna(row.get("L0W")) or row.get("L1W") == 0:
            continue
        change = (row["L0W"] - row["L1W"]) / abs(row["L1W"])
        if abs(change) >= threshold:
            findings.append(f"{idx[2]} / {idx[3]} changed {change:.1%} WoW ({row['L1W']:.2f} to {row['L0W']:.2f}).")
    return findings[:10]


def _find_trends(df: pd.DataFrame) -> list[str]:
    findings = []
    if df.empty:
        return findings
    ordered = sorted(df["week"].dropna().unique(), key=_week_sort_key)
    recent = ordered[-4:]
    wide = df[df["week"].isin(recent)].pivot_table(index=["zone", "metric"], columns="week", values="value", aggfunc="mean")
    for (zone, metric), row in wide.iterrows():
        vals = [row.get(w) for w in recent if not pd.isna(row.get(w))]
        if len(vals) >= 4 and (all(a < b for a, b in zip(vals, vals[1:])) or all(a > b for a, b in zip(vals, vals[1:]))):
            direction = "improved" if vals[-1] > vals[0] else "deteriorated"
            findings.append(f"{zone} / {metric} consistently {direction} across {len(vals)} weeks ({vals[0]:.2f} to {vals[-1]:.2f}).")
    return findings[:10]


def _find_benchmarks(df: pd.DataFrame) -> list[str]:
    if df.empty or "zone_type" not in df:
        return []
    current = df[df["week"] == "L0W"].copy()
    if current.empty:
        return []
    current["peer_avg"] = current.groupby(["country", "zone_type", "metric"])["value"].transform("mean")
    current["gap"] = current["value"] - current["peer_avg"]
    current = current[current["peer_avg"].notna()].sort_values("gap", key=lambda s: s.abs(), ascending=False)
    return [f"{r.zone} / {r.metric} is {r.gap:.2f} vs peer average {r.peer_avg:.2f} in {r.country} {r.zone_type}." for r in current.head(10).itertuples()]


def _find_correlations(df: pd.DataFrame) -> list[str]:
    if df.empty:
        return []
    pivot = df.pivot_table(index=["country", "city", "zone", "week"], columns="metric", values="value", aggfunc="mean")
    corr = pivot.corr(numeric_only=True)
    findings = []
    for i, left in enumerate(corr.columns):
        for right in corr.columns[i + 1 :]:
            val = corr.loc[left, right]
            if pd.notna(val):
                findings.append((abs(val), f"{left} and {right} correlation is {val:.2f}."))
    return [text for _, text in sorted(findings, reverse=True)[:8]]


def _find_opportunities(metrics_df: pd.DataFrame, orders_df: pd.DataFrame) -> list[str]:
    findings = []
    current = metrics_df[metrics_df["week"] == "L0W"]
    if not orders_df.empty:
        orders = orders_df[orders_df["week"] == "L0W"].groupby("zone")["orders"].sum()
        if not orders.empty:
            top_orders = set(orders.sort_values(ascending=False).head(10).index)
            weak = current[current["zone"].isin(top_orders)].sort_values("value").head(5)
            findings.extend([f"{r.zone} has high order volume and weak {r.metric} at {r.value:.2f}." for r in weak.itertuples()])
    pivot = current.pivot_table(index="zone", columns="metric", values="value", aggfunc="mean")
    if {"Lead Penetration", "Perfect Orders"}.issubset(pivot.columns):
        lp_cut = pivot["Lead Penetration"].quantile(0.75)
        po_cut = pivot["Perfect Orders"].quantile(0.25)
        zones = pivot[(pivot["Lead Penetration"] >= lp_cut) & (pivot["Perfect Orders"] <= po_cut)]
        findings.extend([f"{z} has high Lead Penetration ({r['Lead Penetration']:.2f}) but low Perfect Orders ({r['Perfect Orders']:.2f})." for z, r in zones.iterrows()])
    return findings[:10]


def _empty_report() -> str:
    return (
        "# Executive Analytics Report\n\n"
        "## Executive Summary\n- No analytics rows are loaded yet.\n\n"
        "## Anomalies\n- No data available.\n\n## Trends\n- No data available.\n\n"
        "## Benchmarking\n- No data available.\n\n## Correlations\n- No data available.\n\n"
        "## Opportunities\n- No data available.\n\n## Caveats and Limitations\n- Upload CSV files and build the DuckDB database before drawing conclusions.\n"
    )


def _section(title: str, items: list[str], recommendation: str) -> str:
    body = "\n".join(f"- {item} Recommendation: {recommendation}" for item in items) if items else "- No strong signal detected."
    return f"## {title}\n{body}\n"


def _format_report(top: list[str], anomalies: list[str], trends: list[str], benchmarks: list[str], correlations: list[str], opportunities: list[str]) -> str:
    summary = "\n".join(f"- {item}" for item in top) if top else "- No dominant finding detected in the loaded data."
    return "\n".join(
        [
            "# Executive Analytics Report",
            "## Executive Summary",
            summary,
            _section("Anomalies", anomalies, "Inspect recent operational changes and prioritize the largest week-over-week gaps."),
            _section("Trends", trends, "Validate whether the trajectory is structural before reallocating resources."),
            _section("Benchmarking", benchmarks, "Compare local practices against stronger peers in the same country and zone type."),
            _section("Correlations", correlations, "Use these relationships as hypotheses, not causal proof."),
            _section("Opportunities", opportunities, "Target zones where demand scale and operational weakness overlap."),
            "## Caveats and Limitations\n- Results depend on uploaded CSV quality, metric definitions, and week labels. Correlations are descriptive and do not prove causality.",
        ]
    )
