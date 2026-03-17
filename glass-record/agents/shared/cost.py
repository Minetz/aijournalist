"""
Cost tracking for Gemini API calls.

Uses a LangChain callback to intercept token counts from every LLM response,
accumulates them per cycle, and flushes a cost ledger entry to Firestore.

Verify current pricing at https://cloud.google.com/vertex-ai/generative-ai/pricing
"""
import datetime
from typing import Any

import structlog
from google.cloud import firestore
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

log = structlog.get_logger()

# USD per 1M tokens — verify at https://cloud.google.com/vertex-ai/generative-ai/pricing
_PRICING: dict[str, dict[str, float]] = {
    "gemini-3.1-pro-preview": {"input": 3.50,  "output": 10.50},  # verify pricing
    "gemini-1.5-pro-002":     {"input": 3.50,  "output": 10.50},
    "gemini-1.5-flash-002":   {"input": 0.075, "output": 0.30},
    "gemini-2.0-flash":       {"input": 0.10,  "output": 0.40},
}
_DEFAULT_PRICING = {"input": 3.50, "output": 10.50}


def _price_for(model: str) -> dict[str, float]:
    for key, price in _PRICING.items():
        if key in model:
            return price
    return _DEFAULT_PRICING


class BudgetExceededError(Exception):
    """Raised when a journalist's monthly spend has reached the configured limit."""

    def __init__(self, journalist_id: str, spent_usd: float, limit_usd: float) -> None:
        self.journalist_id = journalist_id
        self.spent_usd = spent_usd
        self.limit_usd = limit_usd
        super().__init__(
            f"Monthly budget exceeded for {journalist_id}: "
            f"${spent_usd:.4f} spent of ${limit_usd:.2f} limit"
        )


async def check_monthly_budget(
    db: firestore.AsyncClient,
    journalist_id: str,
    limit_usd: float,
) -> float:
    """
    Sum cost_ledger entries for the current calendar month and raise
    BudgetExceededError if total >= limit_usd.

    Returns the current month's total spend so callers can log it.
    """
    now = datetime.datetime.utcnow()
    month_start = datetime.datetime(now.year, now.month, 1).isoformat()

    docs = await (
        db.collection("journalists")
        .document(journalist_id)
        .collection("cost_ledger")
        .where("recorded_at", ">=", month_start)
        .get()
    )

    spent_usd = sum(d.to_dict().get("cost_usd", 0.0) for d in docs)
    log.info(
        "budget_check",
        journalist_id=journalist_id,
        spent_usd=round(spent_usd, 4),
        limit_usd=limit_usd,
        month=now.strftime("%Y-%m"),
    )

    if spent_usd >= limit_usd:
        raise BudgetExceededError(journalist_id, spent_usd, limit_usd)

    return spent_usd


class CostCallbackHandler(AsyncCallbackHandler):
    """
    Accumulate token usage across all LLM calls in a single cycle.
    Pass an instance as a callback when invoking the graph, then call
    flush_to_firestore() after the cycle completes.
    """

    def __init__(self, journalist_id: str, cycle_id: str, model: str) -> None:
        self.journalist_id = journalist_id
        self.cycle_id = cycle_id
        self.model = model
        self.input_tokens = 0
        self.output_tokens = 0
        self.call_count = 0

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        for generations in response.generations:
            for gen in generations:
                meta = getattr(gen, "generation_info", None) or {}
                usage = meta.get("usage_metadata", {})
                self.input_tokens += usage.get("prompt_token_count", 0)
                self.output_tokens += usage.get("candidates_token_count", 0)
                self.call_count += 1

    @property
    def total_cost_usd(self) -> float:
        price = _price_for(self.model)
        return (
            self.input_tokens / 1_000_000 * price["input"]
            + self.output_tokens / 1_000_000 * price["output"]
        )

    def summary(self) -> dict:
        return {
            "model": self.model,
            "call_count": self.call_count,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
            "cost_usd": round(self.total_cost_usd, 6),
        }

    async def flush_to_firestore(self, db: firestore.AsyncClient) -> None:
        entry = {
            "cycle_id": self.cycle_id,
            "journalist_id": self.journalist_id,
            "recorded_at": datetime.datetime.utcnow().isoformat(),
            **self.summary(),
        }
        await (
            db.collection("journalists")
            .document(self.journalist_id)
            .collection("cost_ledger")
            .document(self.cycle_id)
            .set(entry)
        )
        log.info("cost_recorded", journalist_id=self.journalist_id,
                 cycle_id=self.cycle_id, cost_usd=entry["cost_usd"],
                 total_tokens=entry["total_tokens"])
