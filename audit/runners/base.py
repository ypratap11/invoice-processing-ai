"""Prediction type and the cached, spend-guarded run loop shared by all runners."""
from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from audit.cache import Cache
from audit.spend import SpendLedger


@dataclass
class Prediction:
    """One runner's output for one document, in schema keys with raw strings.

    ``fields`` holds the header fields (``vendor_name`` ... ``total``),
    ``line_items`` dicts with description/quantity/unit_price/amount.
    A failed document has ``error`` set and empty ``fields``/``line_items``,
    so the scorer counts every truth field as missing."""

    doc_id: str
    fields: dict[str, str | None] = field(default_factory=dict)
    line_items: list[dict[str, str | None]] = field(default_factory=list)
    flags: set[str] = field(default_factory=set)
    error: str | None = None
    latency_s: float = 0.0
    cost_usd: float = 0.0

    def as_pred_dict(self) -> dict:
        """The ``pred`` shape ``score_invoice`` expects."""
        return {**self.fields, "line_items": list(self.line_items)}


def _err(doc_id: str, exc: BaseException, latency_s=0.0, cost_usd=0.0) -> Prediction:
    msg = f"{type(exc).__name__}: {exc}"
    return Prediction(doc_id=doc_id, error=msg, latency_s=latency_s, cost_usd=cost_usd)


def run(runner_name: str, fetch: Callable[[Path], dict], adapt: Callable[[dict], Prediction],
        docs, *, cost: Callable[[Path], float] | None = None, ledger: SpendLedger | None = None,
        cache: Cache | None = None, log: Callable[[str], None] = lambda s: None) -> list[Prediction]:
    """Run ``fetch`` + ``adapt`` over ``docs`` (``(doc_id, path, truth)`` tuples).

    - A cached response is reused: no call, no charge.
    - Otherwise the call's cost (``cost(path)``, default ``fetch.cost`` if the
      fetch function carries one, else 0) is charged to the ledger *before*
      the call; ``BudgetExceeded`` propagates and stops the run.
    - A fetch or adapt exception yields ``Prediction(error=...)`` with empty
      fields and the run continues. Failed fetches are not cached (a rerun
      retries them and is charged again).
    - ``latency_s``/``cost_usd`` on each prediction are those of the original
      API call, carried in the cache entry.
    """
    ledger = ledger if ledger is not None else SpendLedger()
    cache = cache if cache is not None else Cache()
    cost = cost or getattr(fetch, "cost", None) or (lambda p: 0.0)
    preds: list[Prediction] = []
    for doc_id, path, _truth in docs:
        path = Path(path)
        entry = cache.get(runner_name, doc_id)
        if entry is None:
            try:
                usd = float(cost(path))
            except Exception as e:  # e.g. unreadable file: cannot price it, do not call
                log(f"{doc_id}: cost estimate failed: {e}")
                preds.append(_err(doc_id, e))
                continue
            ledger.charge(runner_name, usd, note=doc_id)
            t0 = time.perf_counter()
            try:
                resp = fetch(path)
            except Exception as e:
                latency = time.perf_counter() - t0
                log(f"{doc_id}: fetch failed after {latency:.1f}s: {type(e).__name__}: {e}")
                preds.append(_err(doc_id, e, latency, usd))
                continue
            entry = {"response": resp, "latency_s": time.perf_counter() - t0, "cost_usd": usd,
                     "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            cache.put(runner_name, doc_id, entry)
            log(f"{doc_id}: fetched in {entry['latency_s']:.1f}s, charged ${usd:.2f}")
        else:
            log(f"{doc_id}: cache hit")
        try:
            pred = adapt(entry["response"])
        except Exception as e:
            log(f"{doc_id}: adapt failed: {traceback.format_exc(limit=3)}")
            preds.append(_err(doc_id, e, entry["latency_s"], entry["cost_usd"]))
            continue
        preds.append(replace(pred, doc_id=doc_id, latency_s=entry["latency_s"],
                             cost_usd=entry["cost_usd"]))
    return preds
