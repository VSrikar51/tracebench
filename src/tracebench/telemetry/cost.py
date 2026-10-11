"""Model prices from config.yaml, the cost of each model call, and the budget guard."""

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel
from sqlalchemy import text

from tracebench.db import engine

CONFIG_PATH = Path(__file__).resolve().parents[3] / "config.yaml"


class ModelPrice(BaseModel):
    provider: str
    input_per_million: float
    output_per_million: float

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens / 1_000_000 * self.input_per_million
            + output_tokens / 1_000_000 * self.output_per_million
        )


class Budget(BaseModel):
    max_spend_usd_per_provider: float


class AppConfig(BaseModel):
    models: dict[str, ModelPrice]
    budget: Budget


@lru_cache
def load_config() -> AppConfig:
    """Read config.yaml once, check it, and remember the result."""
    return AppConfig.model_validate(yaml.safe_load(CONFIG_PATH.read_text()))


def price_for(model: str) -> ModelPrice:
    """The price of a model. Missing prices are an error, never a silent $0."""
    price = load_config().models.get(model)
    if price is None:
        raise ValueError(f"No price for model '{model}' in config.yaml. Add one before using it.")
    return price


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    return price_for(model).cost(input_tokens, output_tokens)


class BudgetExceeded(Exception):
    """Raised when a provider has used up its spending limit."""


class BudgetGuard:
    """Tracks spending for one provider and stops calls once the limit is reached."""

    def __init__(self, provider: str, limit: float | None = None) -> None:
        self.provider = provider
        self.limit = limit if limit is not None else load_config().budget.max_spend_usd_per_provider
        self.spent = self._spent_in_database()

    def _spent_in_database(self) -> float:
        with engine.connect() as conn:
            total = conn.execute(text("""
                SELECT COALESCE(sum(cost_usd), 0)
                FROM telemetry.llm_calls
                WHERE provider = :provider
            """), {"provider": self.provider}).scalar_one()
        return float(total)

    def check(self) -> None:
        """Call before every model call."""
        if self.spent >= self.limit:
            raise BudgetExceeded(
                f"{self.provider} has spent ${self.spent:.4f} of its ${self.limit:.2f} limit."
            )

    def add(self, amount: float) -> None:
        """Call after every model call."""
        self.spent += amount


_guards: dict[str, BudgetGuard] = {}


def get_budget_guard(provider: str) -> BudgetGuard:
    """One guard per provider for the whole program, so spending adds up across runs."""
    if provider not in _guards:
        _guards[provider] = BudgetGuard(provider)
    return _guards[provider]


if __name__ == "__main__":
    local = cost_usd("qwen3.5:4b", 9656, 308)
    print(f"Damaged-litter run on local qwen3.5:4b: ${local:.6f}")

    paid = ModelPrice(provider="example", input_per_million=1.00, output_per_million=5.00)
    one_run = paid.cost(9656, 308)
    print(f"Same run at $1 in / $5 out per million tokens: ${one_run:.4f}")
    print(f"60 tasks like it: ${one_run * 60:.2f}")

    guard = BudgetGuard("example", limit=0.01)
    guard.add(one_run)
    try:
        guard.check()
    except BudgetExceeded as error:
        print(f"\n The budget guard stopped the next call: {error}")