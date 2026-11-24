"""Disk cache of raw runner responses keyed by (runner, doc_id).

A cached document is never re-sent to a paid API. Layout:
``<root>/<runner>/<doc_id>.json``. The cache directory is gitignored.
"""
from __future__ import annotations

import json
from pathlib import Path

DEFAULT_ROOT = "audit/cache"


class Cache:
    def __init__(self, root=DEFAULT_ROOT):
        self.root = Path(root)

    def _path(self, runner: str, doc_id: str) -> Path:
        return self.root / runner / f"{doc_id}.json"

    def get(self, runner: str, doc_id: str) -> dict | None:
        p = self._path(runner, doc_id)
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def put(self, runner: str, doc_id: str, payload: dict) -> None:
        p = self._path(runner, doc_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(p)
