"""Run harness, spend guard, cache, and Document AI "before" adapter (offline)."""
import json
from pathlib import Path

import pytest

from audit.cache import Cache
from audit.runners.base import Prediction, run
from audit.schema import Invoice, LineItem
from audit.scorer import score_invoice
from audit.spend import BudgetExceeded, SpendLedger

FIXTURE = Path(__file__).parent / "fixtures" / "docai_min.json"


def _docs(tmp_path, n):
    docs = []
    for i in range(1, n + 1):
        p = tmp_path / f"doc-{i}.pdf"
        p.write_bytes(b"%PDF-fake")
        docs.append((f"doc-{i}", p, Invoice(vendor_name="Acme", invoice_id=f"INV-{i}")))
    return docs


def _adapt(resp):
    return Prediction(doc_id="", fields={"vendor_name": resp["vendor"], "invoice_id": resp["id"]},
                      line_items=[], flags=set(), error=None, latency_s=0.0, cost_usd=0.0)


class CountingFetch:
    def __init__(self, fail_on=()):
        self.calls = []
        self.fail_on = set(fail_on)

    def __call__(self, path):
        self.calls.append(path.name)
        if path.name in self.fail_on:
            raise RuntimeError("simulated API error")
        return {"vendor": "Acme", "id": "INV-" + path.stem.split("-")[1]}


def _env(tmp_path, spent=0.0):
    ledger = SpendLedger(path=tmp_path / "cache" / "spend.json", cap_usd=20.0)
    if spent:
        ledger.charge("seed", spent)
    return ledger, Cache(root=tmp_path / "cache")


def test_cache_hit_makes_no_call(tmp_path):
    ledger, cache = _env(tmp_path)
    fetch = CountingFetch()
    docs = _docs(tmp_path, 1)
    for _ in range(2):
        preds = run("fake", fetch, _adapt, docs, cost=lambda p: 0.10, ledger=ledger, cache=cache)
    assert len(fetch.calls) == 1
    assert ledger.total() == pytest.approx(0.10)  # cache hit is not charged again
    assert preds[0].fields["invoice_id"] == "INV-1"
    assert preds[0].cost_usd == pytest.approx(0.10)  # the doc's recorded API cost survives the cache
    # a fresh ledger/cache object over the same files sees the persisted state
    assert SpendLedger(path=tmp_path / "cache" / "spend.json").total() == pytest.approx(0.10)
    assert Cache(root=tmp_path / "cache").get("fake", "doc-1") is not None


def test_budget_exceeded_stops_before_call(tmp_path):
    ledger, cache = _env(tmp_path, spent=19.95)
    fetch = CountingFetch()
    with pytest.raises(BudgetExceeded):
        run("fake", fetch, _adapt, _docs(tmp_path, 1), cost=lambda p: 0.10, ledger=ledger, cache=cache)
    assert fetch.calls == []
    assert ledger.total() == pytest.approx(19.95)


def test_ledger_charge_refuses_over_cap(tmp_path):
    ledger = SpendLedger(path=tmp_path / "spend.json", cap_usd=1.0)
    ledger.charge("a", 0.6)
    with pytest.raises(BudgetExceeded):
        ledger.charge("b", 0.5)
    ledger.charge("b", 0.4)  # exactly at the cap is allowed
    assert ledger.total() == pytest.approx(1.0)


def test_failed_document_counts_as_missing(tmp_path):
    ledger, cache = _env(tmp_path)
    fetch = CountingFetch(fail_on={"doc-2.pdf"})
    docs = _docs(tmp_path, 3)
    preds = run("fake", fetch, _adapt, docs, cost=lambda p: 0.10, ledger=ledger, cache=cache)
    assert [p.doc_id for p in preds] == ["doc-1", "doc-2", "doc-3"]
    assert preds[1].error and "simulated API error" in preds[1].error
    assert preds[1].fields == {} and preds[1].line_items == []
    assert preds[0].error is None and preds[2].error is None
    res = score_invoice(docs[1][2], preds[1].as_pred_dict(), "strict", preds[1].flags, False)
    assert {r.status for r in res} == {"missing"}
    assert cache.get("fake", "doc-2") is None  # failures are not cached


def test_adapter_failure_counts_as_error(tmp_path):
    ledger, cache = _env(tmp_path)

    def bad_adapt(resp):
        raise KeyError("boom")

    preds = run("fake", CountingFetch(), bad_adapt, _docs(tmp_path, 1), cost=lambda p: 0.0,
                ledger=ledger, cache=cache)
    assert preds[0].error and "boom" in preds[0].error and preds[0].fields == {}


def _fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_adapt_before_renames_only():
    from audit.runners.docai import adapt_before
    pred = adapt_before(_fixture())
    assert pred.fields["vendor_name"] == "Acme Corporation"
    assert pred.fields["invoice_id"] == "INV-1001"
    assert pred.fields["invoice_date"] == "04/03/2026"
    assert pred.fields["total"] == "$1,250.00"  # no cleanup
    assert pred.fields["subtotal"] is None and pred.fields["due_date"] is None
    assert pred.line_items == [{"description": "Software License", "quantity": "1",
                                "unit_price": "$1,000.00", "amount": "$1,000.00"}]
    assert pred.error is None


def test_adapt_before_flags_low_confidence():
    from audit.runners.docai import adapt_before
    pred = adapt_before(_fixture())
    assert "total" in pred.flags
    assert "vendor_name" not in pred.flags and "invoice_id" not in pred.flags


def test_header_map_first_match_wins():
    from audit.runners.docai import map_line
    row = {"Item": "Widget", "Description": "ignored (description already mapped)",
           "Quantity": "2", "Rate": "$5.00", "Line Total": "$10.00", "column_5": "x"}
    assert map_line(row) == {"description": "Widget", "quantity": "2",
                             "unit_price": "$5.00", "amount": "$10.00"}
    # "Unit Price" is checked against unit_price before amount's "total"/"amount"
    assert map_line({"Unit Price": "1", "Amount": "2"}) == {
        "description": None, "quantity": None, "unit_price": "1", "amount": "2"}


def test_docai_cost_and_mime(tmp_path):
    from audit.runners.docai import cost_for_pages, mime_type
    assert cost_for_pages(1) == pytest.approx(0.10)
    assert cost_for_pages(10) == pytest.approx(0.10)
    assert cost_for_pages(11) == pytest.approx(0.20)
    assert mime_type(Path("a.PDF")) == "application/pdf"
    assert mime_type(Path("a.png")) == "image/png"
    assert mime_type(Path("a.jpeg")) == "image/jpeg"
    assert mime_type(Path("a.jpg")) == "image/jpeg"


def test_build_results_shape(tmp_path):
    from audit.run_audit import build_results
    truth = Invoice(vendor_name="Acme", invoice_id="INV-1",
                    line_items=[LineItem("A"), LineItem("B")])
    docs = [("doc-1", tmp_path / "doc-1.pdf", truth)]
    preds = [Prediction(doc_id="doc-1", fields={"vendor_name": "Acme", "invoice_id": "INV-9"},
                        line_items=[{"description": "A"}], flags={"invoice_id"}, error=None,
                        latency_s=1.5, cost_usd=0.1)]
    out = build_results("docai-before", "m", docs, preds, spend_usd=0.1)
    assert set(out) >= {"run", "model", "date", "aggregate_strict", "aggregate_lenient",
                        "per_doc", "spend_usd"}
    d = out["per_doc"][0]
    assert d["doc_id"] == "doc-1" and d["latency_s"] == 1.5 and d["cost_usd"] == 0.1
    assert d["pred"]["invoice_id"] == "INV-9" and d["flags"] == ["invoice_id"]
    assert d["truth_lines"] == 2 and d["pred_lines"] == 1
    st = {f["field"]: f for f in d["strict"]["fields"]}
    assert st["invoice_id"] == {"field": "invoice_id", "status": "wrong", "flagged": True}
    assert st["line[1].description"]["status"] == "missing"
    assert out["aggregate_strict"]["n_docs"] == 1
    json.dumps(out)  # serialisable


def test_after_run_requires_invoice_checks():
    from audit.run_audit import invoice_flagger
    assert invoice_flagger("docai-before") is None
