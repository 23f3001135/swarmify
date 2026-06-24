"""Planning stage for the random swarm algorithm.

Planning is pure and synchronous: given a parent size and a reference price it
produces a :class:`SwarmPlan` of child quantities and inter-order delays. Keeping
it separate from execution makes the randomisation easy to unit-test and lets the
caller inspect or veto a plan before any order leaves the process.
"""

import random
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_DOWN, Decimal

from pydantic import BaseModel, model_validator

# Quantisation step for child quantities. Eight decimals covers every crypto
# venue we target; the OMS re-rounds to the symbol's real precision later.
_STEP = Decimal("0.00000001")


class SwarmConfig(BaseModel):
    """Bounds that shape a swarm plan.

    Defaults are deliberately conservative so an unconfigured swarm still
    behaves like a small, well-mannered iceberg.
    """

    min_child_orders: int = 2
    max_child_orders: int = 10
    min_delay_ms: int = 0
    max_delay_ms: int = 1000
    min_notional_usd: Decimal = Decimal("5")
    min_quantity: Decimal = Decimal("0.001")
    seed: int | None = None

    @model_validator(mode="after")
    def _check(self) -> "SwarmConfig":
        if self.min_child_orders < 1:
            raise ValueError("min_child_orders must be >= 1")
        if self.max_child_orders < self.min_child_orders:
            raise ValueError("max_child_orders must be >= min_child_orders")
        if self.min_delay_ms < 0:
            raise ValueError("min_delay_ms must be >= 0")
        if self.max_delay_ms < self.min_delay_ms:
            raise ValueError("max_delay_ms must be >= min_delay_ms")
        if self.min_quantity <= 0:
            raise ValueError("min_quantity must be > 0")
        if self.min_notional_usd < 0:
            raise ValueError("min_notional_usd must be >= 0")
        return self


@dataclass(frozen=True)
class SwarmPlan:
    """A fully resolved swarm: what to send and how long to wait between sends."""

    num_orders: int
    quantities: list[Decimal]
    delays_ms: list[int]

    def total_quantity(self) -> Decimal:
        return sum(self.quantities, Decimal("0"))


class SwarmPlanner:
    """Builds a :class:`SwarmPlan` from a parent order and a reference price."""

    @staticmethod
    def create_plan(
        total_amount: Decimal,
        estimated_price: Decimal,
        config: SwarmConfig,
        rng: random.Random | None = None,
    ) -> SwarmPlan:
        if total_amount <= 0:
            raise ValueError("total_amount must be > 0")
        if estimated_price <= 0:
            raise ValueError("estimated_price must be > 0")

        rng = rng or random.Random(config.seed)

        # Smallest child the venue will accept: the larger of the size floor and
        # the notional floor expressed as a quantity at the reference price. The
        # notional division can be non-terminating, so round it up onto the
        # quantisation step — that keeps it a valid floor and, being finite,
        # makes the arithmetic below exact rather than precision-limited.
        notional_floor = config.min_notional_usd / estimated_price
        min_order = max(config.min_quantity, notional_floor).quantize(
            _STEP, rounding=ROUND_CEILING
        )

        feasible = int(total_amount / min_order)
        if feasible < 1:
            raise ValueError(
                f"total_amount {total_amount} is below the minimum order size "
                f"{min_order} implied by the configured constraints"
            )

        target = rng.randint(config.min_child_orders, config.max_child_orders)
        num_orders = max(1, min(target, feasible))

        quantities = SwarmPlanner._split(total_amount, num_orders, min_order, rng)
        delays_ms = [
            rng.randint(config.min_delay_ms, config.max_delay_ms)
            for _ in range(num_orders - 1)
        ]
        return SwarmPlan(num_orders, quantities, delays_ms)

    @staticmethod
    def _split(
        total: Decimal, n: int, min_order: Decimal, rng: random.Random
    ) -> list[Decimal]:
        """Split ``total`` into ``n`` parts, each >= ``min_order``, summing exactly.

        Every child starts at ``min_order``; the surplus is partitioned at
        ``n - 1`` random cut points so the split is non-uniform and hard to
        fingerprint. The final child is set to ``total`` minus everything already
        allocated, which keeps the sum exact and never drops it below the floor
        (the per-child surplus is clamped so the allocation can never overrun).
        """
        if n == 1:
            return [total]

        surplus = total - min_order * n
        cuts = sorted(Decimal(str(rng.random())) for _ in range(n - 1))

        fractions: list[Decimal] = []
        prev = Decimal("0")
        for cut in cuts:
            fractions.append(cut - prev)
            prev = cut
        fractions.append(Decimal("1") - prev)

        quantities: list[Decimal] = []
        allocated = Decimal("0")
        for frac in fractions[:-1]:
            extra = (surplus * frac).quantize(_STEP, rounding=ROUND_DOWN)
            extra = min(extra, surplus - allocated)
            allocated += extra
            quantities.append(min_order + extra)
        quantities.append(total - sum(quantities, Decimal("0")))
        return quantities
