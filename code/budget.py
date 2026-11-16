"""Per-request spending guard for the runners (paper section 3.6).

Usage: RequestBudget(ceiling, reserve, previous_http_records).observe(http_record).
Each HTTP attempt reserves funds before sending, including retries. Missing costs
and interrupted requests retain the reserve as an estimate, never as zero cost.
This is a conservative scheduling guard, not a billing cap: a request can cost
more than the chosen reserve. A provider-side credit limit remains the hard cap.
"""
import math
import threading


class BudgetReached(Exception):
    """The next HTTP attempt would exceed the scheduling allowance."""


class RequestBudget:
    def __init__(self, ceiling, reserve, history=()):
        if ceiling is not None and (not math.isfinite(ceiling) or ceiling < 0):
            raise ValueError("budget must be finite and nonnegative")
        if not math.isfinite(reserve) or reserve <= 0:
            raise ValueError("reserve must be finite and positive")
        self.ceiling, self.reserve = ceiling, reserve
        self.spent, self.known_cost, self.unknown_attempts = 0.0, 0.0, 0
        self.active, self.lock = {}, threading.Lock()
        for record in history:
            self._observe(record, replay=True)
        # Requests without terminal HTTP records might have been charged.
        self.spent += len(self.active) * self.reserve
        self.unknown_attempts += len(self.active)
        self.active.clear()

    def observe(self, record):
        with self.lock:
            self._observe(record)

    def _observe(self, record, replay=False):
        uid, kind = record["uid"], record["kind"]
        if kind == "request":
            if not replay and self.ceiling is not None and \
                    self.spent + (len(self.active) + 1) * self.reserve > self.ceiling + 1e-12:
                raise BudgetReached("request allowance exhausted")
            if uid in self.active:
                raise ValueError("duplicate active HTTP request ID")
            self.active[uid] = True
            return
        if kind not in ("response", "error"):
            return
        if uid not in self.active:
            raise ValueError("HTTP terminal record has no matching request")
        del self.active[uid]
        body = record.get("body") or {}
        cost = (body.get("usage") or {}).get("cost") if isinstance(body, dict) else None
        try:
            cost = float(cost) if cost is not None and not isinstance(cost, bool) else None
        except (ValueError, TypeError):
            cost = None
        if cost is not None and math.isfinite(cost) and cost >= 0:
            self.spent += cost
            self.known_cost += cost
        else:
            self.spent += self.reserve
            self.unknown_attempts += 1
