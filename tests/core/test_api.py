"""The upload endpoint calls Document AI exactly once per file (no network)."""
import json
from pathlib import Path

from fastapi.testclient import TestClient
from google.cloud import documentai

import src.api.main as main

FIXTURE = Path(__file__).parent / "fixtures" / "docai_multipage.json"


class CountingProcessor:
    def __init__(self):
        self.calls = []

    def __call__(self, content: bytes, mime_type: str):
        self.calls.append((len(content), mime_type))
        return documentai.Document.from_json(FIXTURE.read_text(encoding="utf-8"),
                                             ignore_unknown_fields=True)


def _post(monkeypatch, tmp_path):
    proc = CountingProcessor()
    monkeypatch.setattr(main.docai_client, "process_bytes", proc)
    monkeypatch.setattr(main, "RECENT_PROCESSING_PATH", tmp_path / "recent.json")
    client = TestClient(main.app)
    resp = client.post("/process-invoice",
                       files={"file": ("inv.pdf", b"%PDF-fake", "application/pdf")})
    return proc, resp


def test_process_invoice_calls_document_ai_once(monkeypatch, tmp_path):
    proc, resp = _post(monkeypatch, tmp_path)
    assert resp.status_code == 200
    assert proc.calls == [(len(b"%PDF-fake"), "application/pdf")]


def test_process_invoice_response_shape(monkeypatch, tmp_path):
    _, resp = _post(monkeypatch, tmp_path)
    body = resp.json()
    assert body["success"] is True
    data = body["extracted_data"]
    # old top-level keys kept for the Streamlit frontend
    assert set(data) >= {"vendor_info", "invoice_details", "line_items", "totals", "dates",
                         "addresses"}
    assert data["vendor_info"]["name"] == "Northwind Paper Co."
    assert data["invoice_details"]["invoice_number"] == "INV-7731"
    assert data["totals"]["total_amount"] == "1250.00"
    assert data["dates"]["invoice_date"] == "2026-04-03"
    assert len(data["line_items"]) == 3
    assert data["line_items"][0] == {"description": "A4 paper ream", "quantity": "10",
                                     "unit_price": "4.50", "amount": "45.00"}
    assert isinstance(body["review_required"], bool)
    # fixture: first supplier_name has 0.41 but the 0.88 one is chosen; all checks pass
    assert body["review_required"] is False and body["review_reasons"] == []
    assert json.loads((tmp_path / "recent.json").read_text())["line_items_count"] == 3


def test_review_reasons_include_check_failures(monkeypatch, tmp_path):
    def bad(content, mime_type):
        d = json.loads(FIXTURE.read_text(encoding="utf-8"))
        d["entities"] = [e for e in d["entities"] if e["type"] != "invoice_id"]
        return documentai.Document.from_json(json.dumps(d), ignore_unknown_fields=True)
    monkeypatch.setattr(main.docai_client, "process_bytes", bad)
    monkeypatch.setattr(main, "RECENT_PROCESSING_PATH", tmp_path / "recent.json")
    body = TestClient(main.app).post(
        "/process-invoice", files={"file": ("inv.pdf", b"%PDF", "application/pdf")}).json()
    assert body["review_required"] is True
    assert "missing_required:invoice_id" in body["review_reasons"]


SECRET_PATH = "C:/secret-dir/sa-key-file.json"


def test_credentials_error_does_not_reveal_path(monkeypatch):
    from src.core import docai_client
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", SECRET_PATH)
    docai_client.get_client.cache_clear()
    try:
        docai_client.get_client()
    except RuntimeError as e:
        assert "secret-dir" not in str(e) and "sa-key-file" not in str(e)
        assert str(e) == "Google Cloud credentials are not configured"
    else:
        raise AssertionError("expected RuntimeError")
    finally:
        docai_client.get_client.cache_clear()


def test_verify_credentials_does_not_log_path(monkeypatch, caplog):
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", SECRET_PATH)
    with caplog.at_level("DEBUG"):
        assert main.Config.verify_credentials() is False
    assert "secret-dir" not in caplog.text and "sa-key-file" not in caplog.text


def test_processing_error_message_is_generic(monkeypatch, tmp_path):
    def boom(content, mime_type):
        raise RuntimeError(f"failed reading {SECRET_PATH}")
    monkeypatch.setattr(main.docai_client, "process_bytes", boom)
    monkeypatch.setattr(main, "RECENT_PROCESSING_PATH", tmp_path / "recent.json")
    client = TestClient(main.app)
    body = client.post("/process-invoice",
                       files={"file": ("inv.pdf", b"%PDF", "application/pdf")}).json()
    assert body["success"] is False
    assert "secret-dir" not in json.dumps(body)
    batch = client.post("/batch-process",
                        files=[("files", ("inv.pdf", b"%PDF", "application/pdf"))]).json()
    assert batch["batch_results"][0]["success"] is False
    assert "secret-dir" not in json.dumps(batch)
