"""CLI: run one audit configuration over the test set and write its results.

    python -m audit.run_audit RUN_NAME [--limit N]

RUN_NAME is ``<runner>-<phase>``: runner in {docai, gemini, local}, phase in
{before, after}. Raw responses are cached per runner (``audit/cache/<runner>``)
so an ``after`` run reuses the ``before`` run's responses. ``*-after`` runs
apply ``src.core.invoice_checks.check`` to set ``invoice_flagged``.
Writes ``audit/results/<RUN_NAME>.json``.
"""
from __future__ import annotations

import argparse
import importlib
import json
import statistics
import sys
from datetime import date
from pathlib import Path

from audit.cache import Cache
from audit.generate.testset import REPO, load_testset
from audit.runners.base import Prediction, run
from audit.scorer import aggregate, score_invoice
from audit.spend import SpendLedger

RUNNERS = ("docai", "gemini", "local")
PHASES = ("before", "after")
RUN_NAMES = tuple(f"{r}-{p}" for r in RUNNERS for p in PHASES)
RESULTS_DIR = REPO / "audit" / "results"
CACHE_DIR = REPO / "audit" / "cache"


def ledger_and_cache() -> tuple[SpendLedger, Cache]:
    """The shared spend ledger and response cache, anchored to the repo root
    (not the working directory), like the results directory."""
    return SpendLedger(CACHE_DIR / "spend.json"), Cache(CACHE_DIR)


def parse_run_name(run_name: str) -> tuple[str, str]:
    if run_name not in RUN_NAMES:
        raise SystemExit(f"unknown run {run_name!r}; expected one of {', '.join(RUN_NAMES)}")
    runner, phase = run_name.rsplit("-", 1)
    return runner, phase


def invoice_flagger(run_name: str):
    """None for ``*-before``; for ``*-after`` a function pred_dict -> list of
    check failure reasons. Imported lazily: it exists only from Task 5 on."""
    _, phase = parse_run_name(run_name)
    if phase == "before":
        return None
    try:
        from src.core import invoice_checks
    except ImportError as e:
        raise SystemExit(f"{run_name} needs src.core.invoice_checks (Task 5): {e}") from e
    return invoice_checks.check


def load_adapter(runner: str, phase: str):
    try:
        module = importlib.import_module(f"audit.runners.{runner}")
    except ImportError as e:
        raise SystemExit(f"runner module audit.runners.{runner} not available: {e}") from e
    adapt = getattr(module, f"adapt_{phase}", None) or getattr(module, "adapt", None)
    if adapt is None:
        raise SystemExit(f"audit.runners.{runner} has no adapt_{phase} (or adapt)")
    return module, adapt


def model_for(run_name: str, module) -> tuple[str, dict]:
    """Model id and detail for the results file.

    An ``*-after`` run re-scores the ``*-before`` run's cached responses, so it
    reuses that run's recorded model instead of querying the API (an after run
    makes no network calls). Otherwise ``module.model_info()`` is asked."""
    runner, phase = parse_run_name(run_name)
    before = RESULTS_DIR / f"{runner}-before.json"
    if phase == "after" and before.exists():
        prev = json.loads(before.read_text(encoding="utf-8"))
        info = dict(prev.get("model_detail") or {}, source=before.name)
        return prev.get("model") or runner, info
    info = module.model_info() if hasattr(module, "model_info") else {}
    model = info.get("processor_version") or info.get("model") or info.get("processor") or runner
    return model, info


def _rel(path) -> str:
    try:
        return Path(path).resolve().relative_to(REPO).as_posix()
    except ValueError:
        return str(path)


def _score_json(res) -> dict:
    return {"fields": [{"field": r.field, "status": r.status, "flagged": r.flagged} for r in res],
            "extra_lines": res.extra_lines, "doc_flagged": res.doc_flagged}


def build_results(run_name: str, model, docs, preds: list[Prediction], spend_usd: float,
                  flagger=None, extra: dict | None = None) -> dict:
    by_id = {p.doc_id: p for p in preds}
    scored = {"strict": {}, "lenient": {}}
    per_doc = []
    for doc_id, path, truth in docs:
        p = by_id[doc_id]
        pred = p.as_pred_dict()
        reasons = list(flagger(pred)) if flagger else []
        inv_flag = bool(reasons)
        entry = {"doc_id": doc_id, "file": _rel(path), "tags": list(truth.tags),
                 "error": p.error, "latency_s": round(p.latency_s, 3), "cost_usd": p.cost_usd,
                 "pred": pred, "flags": sorted(p.flags), "invoice_flagged": inv_flag,
                 "check_reasons": reasons, "truth_lines": len(truth.line_items),
                 "pred_lines": len(p.line_items)}
        for mode in ("strict", "lenient"):
            res = score_invoice(truth, pred, mode, p.flags, inv_flag)
            scored[mode][doc_id] = res
            entry[mode] = _score_json(res)
        per_doc.append(entry)
    latencies = [p.latency_s for p in preds if p.error is None]
    out = {
        "run": run_name,
        "model": model,
        "date": date.today().isoformat(),
        "aggregate_strict": aggregate(scored["strict"]),
        "aggregate_lenient": aggregate(scored["lenient"]),
        "per_doc": per_doc,
        "spend_usd": spend_usd,
        "summary": {
            "n_docs": len(docs),
            "n_errors": sum(1 for p in preds if p.error),
            "api_cost_usd": round(sum(p.cost_usd for p in preds), 2),
            "median_latency_s": round(statistics.median(latencies), 3) if latencies else None,
            "docs_fewer_pred_lines_than_truth": sum(
                1 for d in per_doc if d["pred_lines"] < d["truth_lines"]),
        },
    }
    if extra:
        out.update(extra)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_name", choices=RUN_NAMES)
    ap.add_argument("--limit", type=int, default=None, help="only the first N documents")
    args = ap.parse_args(argv)

    runner, phase = parse_run_name(args.run_name)
    flagger = invoice_flagger(args.run_name)  # fail fast, before any paid call
    module, adapt = load_adapter(runner, phase)
    docs = load_testset()
    if args.limit is not None:
        docs = docs[: args.limit]

    ledger, cache = ledger_and_cache()
    print(f"{args.run_name}: {len(docs)} docs; ledger before ${ledger.total():.2f} (cap ${ledger.cap_usd})")
    preds = run(runner, module.fetch, adapt, docs, ledger=ledger, cache=cache,
                log=lambda s: print("  " + s, flush=True))

    model, info = model_for(args.run_name, module)
    out = build_results(args.run_name, model, docs, preds, spend_usd=ledger.total(),
                        flagger=flagger,
                        extra={"model_detail": info, "limit": args.limit,
                               "spend_by_runner": ledger.by_runner()})
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    dest = RESULTS_DIR / f"{args.run_name}.json"
    dest.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    s = out["summary"]
    print(f"wrote {_rel(dest)}: {s['n_docs']} docs, {s['n_errors']} errors, "
          f"ledger total ${ledger.total():.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
