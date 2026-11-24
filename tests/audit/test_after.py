"""Document AI "after" adapter, spend safety on credential failure, repo-anchored paths."""
import json
from pathlib import Path

import pytest

from audit.cache import Cache
from audit.runners.base import run
from audit.schema import Invoice
from audit.spend import SpendLedger

FIXTURE = Path(__file__).resolve().parents[1] / "core" / "fixtures" / "docai_multipage.json"
MIN_FIXTURE = Path(__file__).parent / "fixtures" / "docai_min.json"


def _fixture(path=FIXTURE):
    return json.loads(path.read_text(encoding="utf-8"))


def test_adapt_after_uses_entity_extractor():
    from audit.runners.docai import adapt_after
    pred = adapt_after(_fixture())
    assert pred.fields["vendor_name"] == "Northwind Paper Co."
    assert pred.fields["total"] == "1250.00" and pred.fields["invoice_date"] == "2026-04-03"
    assert len(pred.line_items) == 3
    assert pred.line_items[2]["amount"] == "1198.50"
    assert pred.flags == set()


def test_adapt_after_flags_low_confidence_fields():
    from audit.runners.docai import adapt_after
    d = _fixture()
    for e in d["entities"]:
        if e["type"] == "total_amount":
            e["confidence"] = 0.5
        if e["type"] == "line_item" and e["mentionText"].startswith("Staples"):
            e["properties"][1]["confidence"] = 0.2  # child confidence does not flag
    assert adapt_after(d).flags == {"total"}
    for e in d["entities"]:
        if e["type"] == "line_item" and e["mentionText"].startswith("Staples"):
            e["confidence"] = 0.5  # the line entity's own confidence does
    assert adapt_after(d).flags == {"total", "line_items"}


def test_adapt_before_still_reproduces_the_original_app():
    # the "before" adapter keeps the app's original table-only extraction
    from audit.runners.docai import adapt_before
    pred = adapt_before(_fixture(MIN_FIXTURE))
    assert pred.fields["total"] == "$1,250.00"
    assert pred.line_items[0]["description"] == "Software License"
    # and on an entity-only response it extracts no lines, as measured
    assert adapt_before(_fixture()).line_items == []


def test_invoice_flagger_for_after_runs():
    from audit.run_audit import invoice_flagger
    from src.core.invoice_checks import check
    assert invoice_flagger("docai-after") is check


def test_credentials_failure_records_no_spend(tmp_path, monkeypatch):
    from audit.runners import docai

    def no_creds():
        raise RuntimeError("Google Cloud credentials not found")
    monkeypatch.setattr(docai.docai_client, "get_client", no_creds)
    called = []
    monkeypatch.setattr(docai.docai_client, "process_bytes", lambda *a: called.append(a))
    p = tmp_path / "doc-1.pdf"
    p.write_bytes(b"%PDF-fake")
    ledger = SpendLedger(path=tmp_path / "spend.json")
    preds = run("docai", docai.fetch, docai.adapt_after, [("doc-1", p, Invoice())],
                ledger=ledger, cache=Cache(root=tmp_path / "cache"))
    assert ledger.total() == 0.0
    assert not (tmp_path / "spend.json").exists()
    assert called == []
    assert preds[0].error and "credentials" in preds[0].error


def test_ledger_and_cache_anchored_to_repo(tmp_path, monkeypatch):
    from audit.generate.testset import REPO
    from audit.run_audit import ledger_and_cache
    monkeypatch.chdir(tmp_path)
    ledger, cache = ledger_and_cache()
    assert ledger.path == REPO / "audit" / "cache" / "spend.json"
    assert cache.root == REPO / "audit" / "cache"
    assert ledger.path.is_absolute() and cache.root.is_absolute()


def test_after_run_reuses_before_model_info(tmp_path, monkeypatch):
    import audit.run_audit as ra
    (tmp_path / "docai-before.json").write_text(json.dumps(
        {"model": "pv-1", "model_detail": {"processor": "p", "processor_version": "pv-1"}}))
    monkeypatch.setattr(ra, "RESULTS_DIR", tmp_path)

    class NoNetwork:
        def model_info(self):
            raise AssertionError("after run must not query the API for model info")
    model, info = ra.model_for("docai-after", NoNetwork())
    assert model == "pv-1"
    assert info["processor_version"] == "pv-1"
    assert info["source"] == "docai-before.json"
