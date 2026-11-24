"""process_invoice agent tool: only files inside UPLOAD_DIR are read (no network).

langchain / sqlalchemy are app dependencies that the audit venv does not
carry, so they and ``src.database`` are stubbed for the import."""
import importlib
import json
import os
import sys
import types

import pytest

import src.api.main as main


class _FakeSession:
    def close(self):
        pass


@pytest.fixture
def tools(monkeypatch, tmp_path):
    lc, lct = types.ModuleType("langchain"), types.ModuleType("langchain.tools")
    lct.BaseTool = type("BaseTool", (), {})
    lc.tools = lct
    sa, sao = types.ModuleType("sqlalchemy"), types.ModuleType("sqlalchemy.orm")
    sao.Session = object
    sa.orm = sao
    db = types.ModuleType("src.database")
    saved = []
    db.save_invoice_to_db = lambda rec, s: saved.append(rec) or types.SimpleNamespace(id=7)
    db.get_db = db.search_invoices_by_vendor = db.get_recent_invoices = lambda *a: []
    db.get_invoices_by_amount_range = lambda *a: []
    db.SessionLocal = _FakeSession
    for name, mod in {"langchain": lc, "langchain.tools": lct, "sqlalchemy": sa,
                      "sqlalchemy.orm": sao, "src.database": db}.items():
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.delitem(sys.modules, "src.agents.tools", raising=False)
    mod = importlib.import_module("src.agents.tools")

    upload = tmp_path / "uploads"
    upload.mkdir()
    monkeypatch.setattr(main, "UPLOAD_DIR", upload)
    calls = []

    def fake_process(content, mime_type):
        calls.append((content, mime_type))
        return {"invoice": {"vendor_name": "V", "invoice_id": "1", "invoice_date": "2026-04-03",
                            "total": "10.00", "line_items": []},
                "extracted_data": {}, "confidence_scores": {"total": 0.9},
                "review_required": False, "review_reasons": []}
    monkeypatch.setattr(main, "process_invoice_bytes", fake_process)
    yield types.SimpleNamespace(tool=mod.InvoiceProcessingTool(), upload=upload, calls=calls,
                                saved=saved, root=tmp_path)
    sys.modules.pop("src.agents.tools", None)


def test_valid_file_inside_upload_dir_is_processed(tools):
    (tools.upload / "inv.pdf").write_bytes(b"%PDF-1")
    out = json.loads(tools.tool._run("inv.pdf"))
    assert tools.calls == [(b"%PDF-1", "application/pdf")]
    assert out["filename"] == "inv.pdf" and out["invoice"]["total"] == "10.00"
    assert out["database_id"] == 7 and tools.saved[0]["total_amount"] == 10.0
    # an absolute path inside the upload dir is fine too
    json.loads(tools.tool._run(str(tools.upload / "inv.pdf")))
    assert len(tools.calls) == 2


@pytest.mark.parametrize("arg", ["../.env", "../secret.pdf", "sub/../../secret.pdf"])
def test_path_outside_upload_dir_rejected(tools, arg):
    (tools.root / ".env").write_text("GOOGLE_APPLICATION_CREDENTIALS=SECRETVALUE")
    (tools.root / "secret.pdf").write_bytes(b"SECRETVALUE")
    out = tools.tool._run(arg)
    assert out.startswith("❌") and "SECRETVALUE" not in out
    assert tools.calls == []


def test_absolute_path_outside_upload_dir_rejected(tools):
    secret = tools.root / "secret.pdf"
    secret.write_bytes(b"SECRETVALUE")
    out = tools.tool._run(str(secret))
    assert out.startswith("❌") and "SECRETVALUE" not in out and tools.calls == []


def test_symlink_rejected(tools):
    secret = tools.root / "secret.pdf"
    secret.write_bytes(b"SECRETVALUE")
    link = tools.upload / "link.pdf"
    try:
        os.symlink(secret, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not available")
    out = tools.tool._run("link.pdf")
    assert out.startswith("❌") and "SECRETVALUE" not in out and tools.calls == []


def test_oversize_rejected(tools, monkeypatch):
    monkeypatch.setattr(main.config, "MAX_FILE_SIZE", 10)
    (tools.upload / "big.pdf").write_bytes(b"x" * 11)
    out = tools.tool._run("big.pdf")
    assert out.startswith("❌") and "too large" in out.lower() and tools.calls == []


def test_non_file_and_unsupported_extension_rejected(tools):
    (tools.upload / "dir.pdf").mkdir()
    (tools.upload / "notes.txt").write_text("hello")
    for arg in ("dir.pdf", "notes.txt", "missing.pdf"):
        out = tools.tool._run(arg)
        assert out.startswith("❌"), arg
    assert tools.calls == []
