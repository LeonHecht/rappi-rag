from pathlib import Path

from backend.app.core.config import settings
from backend.app.services import analytics


def write_sample_csvs(tmp_path: Path) -> tuple[Path, Path]:
    metrics = tmp_path / "metrics.csv"
    metrics.write_text(
        "COUNTRY,CITY,ZONE,ZONE_TYPE,ZONE_PRIORITIZATION,METRIC,L2W_VALUE,L1W_VALUE,L0W_VALUE\n"
        "Mexico,Bogota,Chapinero,Wealthy,P1,Lead Penetration,10,12,15\n"
        "Mexico,Bogota,Chapinero,Wealthy,P1,Perfect Orders,90,85,80\n"
        "Mexico,Bogota,Centro,Non Wealthy,P2,Gross Profit UE,5,6,7\n",
        encoding="utf-8",
    )
    orders = tmp_path / "orders.csv"
    orders.write_text(
        "COUNTRY,CITY,ZONE,METRIC,L2W,L1W,L0W\n"
        "Mexico,Bogota,Chapinero,Orders,100,120,150\n"
        "Mexico,Bogota,Centro,Orders,60,70,90\n",
        encoding="utf-8",
    )
    return metrics, orders


def setup_analytics(tmp_path, monkeypatch):
    data_dir = tmp_path / "analytics"
    monkeypatch.setattr(settings, "ANALYTICS_DATA_DIR", str(data_dir))
    monkeypatch.setattr(settings, "ANALYTICS_DB_PATH", str(data_dir / "analytics.duckdb"))
    monkeypatch.setattr(settings, "ANALYTICS_METRIC_CONFIG", "backend/config/rappi_metrics.yaml")
    monkeypatch.setattr(settings, "ANALYTICS_MAX_ROWS", 50)
    return write_sample_csvs(tmp_path)


def test_csv_loading_and_wide_to_long(tmp_path, monkeypatch):
    metrics, orders = setup_analytics(tmp_path, monkeypatch)
    metric_result = analytics.load_csv_to_duckdb(metrics)
    order_result = analytics.load_csv_to_duckdb(orders)

    assert metric_result["loaded"] is True
    assert metric_result["rows"] == 9
    assert order_result["loaded"] is True
    assert order_result["rows"] == 6

    result = analytics.run_sql("SELECT metric, week, value FROM metrics_long WHERE zone = 'Chapinero' ORDER BY metric, week")
    assert result["row_count"] == 6
    assert result["rows"][0]["week"] == "L0W"


def test_csv_loading_handles_windows_1252_encoding(tmp_path, monkeypatch):
    setup_analytics(tmp_path, monkeypatch)
    metrics = tmp_path / "metrics_cp1252.csv"
    metrics.write_bytes(
        (
            "COUNTRY,CITY,ZONE,ZONE_TYPE,ZONE_PRIORITIZATION,METRIC,L0W_VALUE\n"
            'Mexico,Bogota,"Zona “Norte”",Wealthy,P1,Lead Penetration,15\n'
        ).encode("cp1252")
    )

    result = analytics.load_csv_to_duckdb(metrics)

    assert result["loaded"] is True
    rows = analytics.run_sql("SELECT zone, metric, value FROM metrics_long")
    assert rows["rows"][0]["zone"] == "Zona “Norte”"


def test_csv_loading_accepts_roll_week_columns(tmp_path, monkeypatch):
    setup_analytics(tmp_path, monkeypatch)
    metrics = tmp_path / "metrics_roll.csv"
    metrics.write_text(
        "COUNTRY,CITY,ZONE,ZONE_TYPE,ZONE_PRIORITIZATION,METRIC,L1W_ROLL,L0W_ROLL\n"
        "MX,Mexicali,MXL_Universidad,Wealthy,Prioritized,Lead Penetration,0.82,0.91\n",
        encoding="utf-8",
    )

    result = analytics.load_csv_to_duckdb(metrics)

    assert result["loaded"] is True
    assert result["table"] == "metrics_long"
    rows = analytics.run_sql(
        "SELECT zone, metric, week, value FROM metrics_long WHERE week = 'L0W'"
    )
    assert rows["rows"] == [
        {
            "zone": "MXL_Universidad",
            "metric": "Lead Penetration",
            "week": "L0W",
            "value": 0.91,
        }
    ]


def test_describe_schema_returns_expected_metadata(tmp_path, monkeypatch):
    metrics, orders = setup_analytics(tmp_path, monkeypatch)
    analytics.load_csv_to_duckdb(metrics)
    analytics.load_csv_to_duckdb(orders)

    schema = analytics.describe_schema()
    assert "metrics_long" in schema["tables"]
    assert "orders_long" in schema["tables"]
    assert "Lead Penetration" in schema["metrics"]
    assert "Mexico" in schema["countries"]
    assert "L0W" in schema["weeks"]
    assert any(c["name"] == "value" for c in schema["columns"]["metrics_long"])


def test_validate_metric_name_maps_approximate_names(tmp_path, monkeypatch):
    metrics, _orders = setup_analytics(tmp_path, monkeypatch)
    analytics.load_csv_to_duckdb(metrics)

    assert analytics.validate_metric_name("lead penetration")["match"] == "Lead Penetration"
    assert analytics.validate_metric_name("gross profit")["match"] == "Gross Profit UE"
    assert analytics.validate_metric_name("Perfect Order")["match"] == "Perfect Orders"


def test_run_sql_allows_select_and_rejects_destructive_sql(tmp_path, monkeypatch):
    metrics, _orders = setup_analytics(tmp_path, monkeypatch)
    analytics.load_csv_to_duckdb(metrics)

    allowed = analytics.run_sql("SELECT zone, metric FROM metrics_long")
    rejected = analytics.run_sql("DROP TABLE metrics_long")
    rejected_insert = analytics.run_sql("INSERT INTO metrics_long VALUES ('x')")

    assert allowed["row_count"] > 0
    assert "error" in rejected
    assert "error" in rejected_insert


def test_generate_executive_report_returns_required_sections(tmp_path, monkeypatch):
    metrics, orders = setup_analytics(tmp_path, monkeypatch)
    analytics.load_csv_to_duckdb(metrics)
    analytics.load_csv_to_duckdb(orders)

    report = analytics.generate_executive_report()
    for section in [
        "Executive Summary",
        "Anomalies",
        "Trends",
        "Benchmarking",
        "Correlations",
        "Opportunities",
        "Caveats and Limitations",
    ]:
        assert section in report
