"""The price table: USD per million tokens by model, matched by glob, with the date the figures were taken.

    as_of: 2026-10-10
    currency: USD
    models:
      - match: "gpt-4o-mini*"
        input_per_1m: 0.15
        output_per_1m: 0.60

The Kit ships no provider price list as fact: list prices change and differ by region, tier and caching. The
example table in examples/ticket-triage-agent/prices.yaml is labelled as an example. Tokens on a model with no
matching row are counted as *unpriced* and reported as a share of all tokens, so an understated cost is visible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from readiness_kit.util import KitError, glob_match, read_yaml


@dataclass
class Price:
    match: str
    input_per_1m: float
    output_per_1m: float
    cached_input_per_1m: float | None = None


@dataclass
class PriceTable:
    prices: list[Price] = field(default_factory=list)
    as_of: str | None = None
    currency: str = "USD"
    path: str | None = None

    def find(self, model: str | None) -> Price | None:
        if not model:
            return None
        for p in self.prices:
            if glob_match(model, p.match):
                return p
        return None

    def cost(self, model: str | None, input_tokens: int, output_tokens: int) -> float | None:
        p = self.find(model)
        if p is None:
            return None
        return input_tokens / 1e6 * p.input_per_1m + output_tokens / 1e6 * p.output_per_1m


def load_prices(path: str | Path | None) -> PriceTable:
    if path is None:
        return PriceTable()
    p = Path(path)
    if not p.exists():
        raise KitError(f"price table not found: {p}")
    data: Any = read_yaml(p) or {}
    if not isinstance(data, dict) or not isinstance(data.get("models"), list):
        raise KitError(f"{p}: a price table is a YAML object with a 'models' list")
    prices = []
    for m in data["models"]:
        try:
            prices.append(
                Price(
                    match=str(m["match"]),
                    input_per_1m=float(m["input_per_1m"]),
                    output_per_1m=float(m["output_per_1m"]),
                    cached_input_per_1m=m.get("cached_input_per_1m"),
                )
            )
        except (KeyError, TypeError, ValueError) as e:
            raise KitError(f"{p}: each model needs match, input_per_1m and output_per_1m ({e})") from e
    return PriceTable(
        prices=prices,
        as_of=str(data.get("as_of")) if data.get("as_of") else None,
        currency=str(data.get("currency", "USD")),
        path=str(p),
    )
