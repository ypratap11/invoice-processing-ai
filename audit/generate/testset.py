"""Load the labeled test set listed in ``audit/testset/manifest.csv``.

Each manifest row names a document ``file`` (relative to the test-set root);
its truth is ``<same directory>/<doc_id>.json``.
"""
from __future__ import annotations

import csv
from pathlib import Path

from audit.schema import Invoice, load_invoice

REPO = Path(__file__).resolve().parents[2]
MANIFEST_COLUMNS = ["doc_id", "source", "file", "license", "tags"]


def truth_path(root: Path, row: dict) -> Path:
    return (root / row["file"]).parent / f"{row['doc_id']}.json"


def load_testset(root="audit/testset") -> list[tuple[str, Path, Invoice]]:
    root = Path(root)
    if not root.is_absolute() and not root.exists():
        root = REPO / root
    with (root / "manifest.csv").open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return [(r["doc_id"], root / r["file"], load_invoice(truth_path(root, r))) for r in rows]
