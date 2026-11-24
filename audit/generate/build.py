"""Write the generated test set and its manifest rows.

    audit/.venv/Scripts/python -m audit.generate.build

Writes audit/testset/generated/<doc_id>.json + <doc_id>.pdf (or .png for
``scanned`` documents) and rewrites the ``generated`` rows of
audit/testset/manifest.csv, keeping any rows from other sources (public).
Re-running is deterministic (same seed -> byte-identical files).
"""
from __future__ import annotations

import csv
import tempfile
from pathlib import Path

from audit.generate.generator import doc_id_for, generate_invoices, layout_for
from audit.generate.render import render_pdf, render_scanned
from audit.generate.testset import MANIFEST_COLUMNS, REPO
from audit.schema import save_invoice

ROOT = REPO / "audit" / "testset"
GEN_LICENSE = "generated-synthetic (no third-party content)"


def main() -> None:
    out = ROOT / "generated"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("gen-*"):
        old.unlink()
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, inv in enumerate(generate_invoices()):
            doc_id, layout = doc_id_for(i), layout_for(i)
            save_invoice(inv, out / f"{doc_id}.json")
            if "scanned" in inv.tags:
                pdf = Path(tmp) / f"{doc_id}.pdf"
                pages = render_pdf(inv, layout, pdf)
                render_scanned(pdf, out / f"{doc_id}.png", seed=i)
                name = f"{doc_id}.png"
            else:
                pages = render_pdf(inv, layout, out / f"{doc_id}.pdf")
                name = f"{doc_id}.pdf"
            assert 1 <= pages <= 10
            rows.append({"doc_id": doc_id, "source": "generated",
                         "file": f"generated/{name}", "license": GEN_LICENSE,
                         "tags": ";".join(inv.tags)})
            print(doc_id, f"layout={layout}", f"pages={pages}", name, ";".join(inv.tags))
    manifest = ROOT / "manifest.csv"
    keep = []
    if manifest.exists():
        with manifest.open(encoding="utf-8", newline="") as f:
            keep = [r for r in csv.DictReader(f) if r["source"] != "generated"]
    with manifest.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS)
        w.writeheader()
        w.writerows(rows + keep)


if __name__ == "__main__":
    main()
