# Invoice accuracy audit: how to run it

The results and what they mean are in [`REPORT.md`](REPORT.md) (two-page PDF: [`REPORT.pdf`](REPORT.pdf)).
This file is about reproducing them.

## What is here

| Path | What it is |
|---|---|
| `testset/` | 53 invoices with truth JSON; `manifest.csv` lists them, `SOURCES.md` gives sources, licences and label corrections |
| `generate/` | Generator for the 40 synthetic invoices (`python -m audit.generate.build` rebuilds the PDFs byte-for-byte; the scanned PNGs were shown to rebuild identically on the build machine only) |
| `scorer.py`, `normalize.py` | Scoring rules, frozen at git tag `audit-scoring-frozen` |
| `runners/` | `docai.py` (the app's Document AI path; `docai_legacy.py` is the original extractor, kept unchanged), `gemini.py` |
| `run_audit.py` | Runs one configuration over the test set and writes `results/<run>.json` |
| `results/` | Committed results: every prediction, every per-field score, aggregates, cost and latency |
| `report/` | `charts.py` (PNG charts) and `make_pdf.py` (REPORT.pdf) |
| `cache/` | Raw API responses and the spend ledger. **Not committed** (gitignored) |

## Setup

Python 3.11+ on Windows, macOS or Linux.

```bash
python -m venv audit/.venv
audit/.venv/Scripts/python -m pip install -r audit/requirements.txt   # Windows
# audit/.venv/bin/python -m pip install -r audit/requirements.txt     # macOS / Linux
```

`requirements.txt` lists the direct dependencies. `requirements.lock` pins the exact versions the audit
was run with (from `uv pip freeze`); install from it instead to reproduce the environment exactly:
`audit/.venv/Scripts/python -m pip install -r audit/requirements.lock`.

Run every command from the repository root. Tests (offline, no Google account needed):

```bash
audit/.venv/Scripts/python -m pytest tests/audit tests/core
```

## Google Cloud auth (only for new API calls)

1. A Google Cloud project with the Document AI API enabled and an **Invoice Parser** processor
   (the audit used version `pretrained-invoice-v2.0-2023-12-06`, region `us`). For Gemini, the Vertex AI API too.
2. Log in with application-default credentials and set the quota project:
   ```bash
   gcloud auth application-default login
   gcloud auth application-default set-quota-project YOUR_PROJECT
   ```
3. In `.env` at the repository root (gitignored; never commit it):
   ```
   GCP_PROJECT_ID=YOUR_PROJECT
   GCP_LOCATION=us
   GCP_PROCESSOR_ID=YOUR_PROCESSOR_ID
   GOOGLE_APPLICATION_CREDENTIALS=<path to the application-default credentials JSON gcloud wrote>
   ```
   The app checks that this file exists, so point it at the ADC file (or a service-account key you keep
   outside the repo).
4. The Gemini runner's project and endpoint are constants at the top of `audit/runners/gemini.py`
   (`PROJECT`, `MODEL`, `LOCATION = "global"`). Change `PROJECT` to yours.

## Running

```bash
audit/.venv/Scripts/python -m audit.run_audit docai-before --limit 1   # smoke test, one paid call
audit/.venv/Scripts/python -m audit.run_audit docai-before             # 53 documents
audit/.venv/Scripts/python -m audit.run_audit docai-after              # no API calls once docai-before is cached
audit/.venv/Scripts/python -m audit.run_audit gemini-before
audit/.venv/Scripts/python -m audit.run_audit gemini-after             # no API calls once gemini-before is cached
audit/.venv/Scripts/python -m audit.report.charts                      # audit/report/*.png
audit/.venv/Scripts/python -m audit.report.make_pdf                    # audit/REPORT.pdf
```

Run names are `<runner>-<phase>`: runner `docai` or `gemini` (`local` is reserved; the local-model run was
deferred), phase `before` (no checks) or `after` (deterministic checks from `src/core/invoice_checks.py`).

## Cost and the spend guard

- Every paid call is charged to `audit/cache/spend.json` **before** it is made. The ledger refuses any call that
  would take the total over **$20**.
- Document AI Invoice Parser: $0.10 per document up to 10 pages. A full run is 53 documents, **$5.30**.
- Gemini (`gemini-3.8-flash`, `global` endpoint): actual usage was **$0.314** for 53 documents at the
  introductory price of $0.75 / $3.75 per million input / output tokens, which Google lists as rising to
  $1.50 / $7.50 on 2027-01-01. The ledger pre-charges a conservative estimate (about $1.75 for 53 documents);
  the results file records the actual cost as `summary.api_cost_usd` and the estimate as
  `summary.charged_estimate_usd`.
- This audit's ledger total for all runs and tests: $7.09, paid from Google Cloud free-trial credit.

## Re-running for free

Raw responses are cached per runner and document in `audit/cache/<runner>/<doc_id>.json`. A run finds a cached
response and makes no call, so:

- On a machine that has the cache, any run (and any scoring change) re-runs at **$0**.
- `*-after` runs share the `*-before` run's cache, so after a `*-before` run they make no API calls.
- The cache is **not in git** (it is paid API output, about 13 MB). Without it, the first run of each runner
  pays again. You can still check every published number without any API: `results/*.json` holds each
  prediction exactly as the system returned it, so it can be re-scored with `audit.scorer.score_invoice`
  against the truth from `audit.generate.testset.load_testset()`.

## Rules for changing anything

- Do not change `scorer.py` or `normalize.py` without recording it in REPORT.md section 9. Check with
  `git diff --stat audit-scoring-frozen HEAD -- audit/scorer.py audit/normalize.py`.
- Do not edit truth files to make a system look better. If a label is wrong, fix it and record it in
  `testset/SOURCES.md`.
