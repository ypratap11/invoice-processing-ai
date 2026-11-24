"""Report charts: written from results JSON, robust to None field accuracies."""
import json

from audit.report.charts import make_charts

FIELDS = ["vendor_name", "invoice_id", "invoice_date", "due_date", "currency",
          "subtotal", "tax_total", "total",
          "line.description", "line.quantity", "line.unit_price", "line.amount"]


def _agg(acc, silent_rate, review_rate, none_field=None):
    fa = {f: acc for f in FIELDS}
    if none_field:
        fa[none_field] = None  # a field scored in no document
    return {"field_accuracy": fa, "field_n": {f: (0 if f == none_field else 5) for f in FIELDS},
            "invoice_fully_correct_pct": 100.0 * acc,
            "silent_errors": {"count": 1, "rate": silent_rate},
            "missing": {"count": 0, "rate": 0.0},
            "review_rate": review_rate, "extra_lines": 0, "n_docs": 5}


def _result(run, acc, silent, review, cost, latency, none_field=None):
    agg = _agg(acc, silent, review, none_field)
    return {"run": run, "model": run.split("-")[0], "date": "2026-11-23",
            "aggregate_strict": agg, "aggregate_lenient": agg, "per_doc": [],
            "summary": {"n_docs": 5, "n_errors": 0, "api_cost_usd": cost,
                        "median_latency_s": latency}}


def test_make_charts_writes_pngs(tmp_path):
    res = tmp_path / "results"
    res.mkdir()
    fixtures = [_result("docai-before", 0.2, 0.08, 0.6, 0.5, 4.0, none_field="due_date"),
                _result("docai-after", 0.8, 0.02, 0.9, 0.5, 4.0),
                _result("gemini-after", 0.95, 0.001, 0.1, 0.03, 8.0, none_field="line.quantity")]
    for r in fixtures:
        (res / f"{r['run']}.json").write_text(json.dumps(r), encoding="utf-8")
    out = tmp_path / "charts"

    paths = make_charts(res, out)

    names = sorted(p.name for p in paths)
    assert names == ["before_after.png", "models.png"]
    for p in paths:
        assert p.exists() and p.stat().st_size > 1000
        assert p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_make_charts_skips_missing_runs(tmp_path):
    """Only docai-after and gemini-after present: models.png still renders,
    before_after.png needs docai-before and is skipped."""
    res = tmp_path / "results"
    res.mkdir()
    for r in [_result("docai-after", 0.8, 0.02, 0.9, 0.5, 4.0),
              _result("gemini-after", 0.95, 0.001, 0.1, 0.03, 8.0)]:
        (res / f"{r['run']}.json").write_text(json.dumps(r), encoding="utf-8")
    paths = make_charts(res, tmp_path / "charts")
    assert [p.name for p in paths] == ["models.png"]
