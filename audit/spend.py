"""Spend ledger with a hard cap, persisted as JSON.

Every paid API call is charged here *before* it is made; a charge that would
take the total over the cap raises ``BudgetExceeded`` and nothing is recorded.
The ledger is shared by all runners (one file, one cap).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

DEFAULT_PATH = "audit/cache/spend.json"
DEFAULT_CAP_USD = 20.0


class BudgetExceeded(RuntimeError):
    pass


class SpendLedger:
    def __init__(self, path=DEFAULT_PATH, cap_usd: float = DEFAULT_CAP_USD):
        self.path = Path(path)
        self.cap_usd = cap_usd

    def _entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8")).get("entries", [])

    def _sum(self, entries) -> Decimal:
        # Decimal over the stored strings so 0.1 * 53 adds up exactly
        return sum((Decimal(e["usd"]) for e in entries), Decimal("0"))

    def total(self) -> float:
        return float(self._sum(self._entries()))

    def by_runner(self) -> dict[str, float]:
        out: dict[str, Decimal] = {}
        for e in self._entries():
            out[e["runner"]] = out.get(e["runner"], Decimal("0")) + Decimal(e["usd"])
        return {k: float(v) for k, v in out.items()}

    def charge(self, runner: str, usd: float, note: str = "") -> None:
        amount = Decimal(str(usd))
        if amount < 0:
            raise ValueError("charge must be non-negative")
        entries = self._entries()
        new_total = self._sum(entries) + amount
        if new_total > Decimal(str(self.cap_usd)):
            raise BudgetExceeded(
                f"charging ${amount} for {runner!r} would bring spend to ${new_total} "
                f"(cap ${self.cap_usd}); call not made")
        entries.append({"runner": runner, "usd": str(amount), "note": note,
                        "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"cap_usd": self.cap_usd, "entries": entries}, indent=1),
                       encoding="utf-8")
        tmp.replace(self.path)
