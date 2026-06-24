"""Random swarm execution: work a parent order as randomised child slices.

Splitting a large order across a random number of children, with random sizes
and random gaps, keeps the working order off the tape as a single recognisable
print. The plan is built once (see :mod:`.swarm_planner`) and replayed here.
"""

import asyncio
import time
import uuid
from collections.abc import AsyncGenerator
from decimal import Decimal
from typing import Any

import structlog

from ..core.models import AlgoOrder, Order
from ..core.types import OrderSide, OrderStatus, OrderType, TimeInForce
from .base import ExecutionAlgo
from .swarm_planner import SwarmConfig, SwarmPlan, SwarmPlanner

logger = structlog.get_logger(__name__)


class RandomSwarmAlgo(ExecutionAlgo):
    """Execute a parent order as a randomised swarm of child orders.

    Beyond slicing, the algorithm tracks fills so it can report a weighted
    average entry, flag under-filled executions against ``min_fill_percent``,
    and derive a protective stop from the realised entry price.
    """

    name = "random_swarm"

    def __init__(
        self,
        algo_order: AlgoOrder,
        config: SwarmConfig | None = None,
        min_fill_percent: Decimal = Decimal("95.0"),
    ) -> None:
        super().__init__(algo_order)
        self.config = config or SwarmConfig()
        self.min_fill_percent = min_fill_percent

        self.plan: SwarmPlan | None = None

        self._fills: list[dict[str, Decimal]] = []
        self._total_filled = Decimal("0")
        self._total_cost = Decimal("0")

    async def next_slice(self, current_market_price: Decimal) -> AsyncGenerator[Order]:
        """Yield child orders, sleeping the planned delay before each."""
        if self.plan is None:
            self._build_plan(current_market_price)
        assert self.plan is not None

        for i, qty in enumerate(self.plan.quantities):
            if i > 0:
                delay_ms = self.plan.delays_ms[i - 1]
                if delay_ms > 0:
                    logger.debug(
                        "swarm.delay",
                        parent_id=self.parent_order.id,
                        slice=i + 1,
                        delay_ms=delay_ms,
                    )
                    await asyncio.sleep(delay_ms / 1000.0)

            child = self._build_child(i, qty, current_market_price)
            logger.info(
                "swarm.submit",
                parent_id=self.parent_order.id,
                child_id=child.id,
                slice=f"{i + 1}/{self.plan.num_orders}",
                amount=str(qty),
                price=str(current_market_price),
            )
            yield child

        logger.info(
            "swarm.plan_exhausted",
            parent_id=self.parent_order.id,
            num_orders=self.plan.num_orders,
        )

    def _build_plan(self, current_market_price: Decimal) -> None:
        logger.info(
            "swarm.start",
            parent_id=self.parent_order.id,
            symbol=self.parent_order.symbol,
            side=self.parent_order.side.value,
            total_amount=str(self.parent_order.total_amount),
            reference_price=str(current_market_price),
        )
        self.plan = SwarmPlanner.create_plan(
            total_amount=self.parent_order.total_amount,
            estimated_price=current_market_price,
            config=self.config,
        )
        logger.info(
            "swarm.plan_ready",
            parent_id=self.parent_order.id,
            num_orders=self.plan.num_orders,
            quantities=[str(q) for q in self.plan.quantities],
            delays_ms=self.plan.delays_ms,
        )

    def _build_child(self, index: int, qty: Decimal, price: Decimal) -> Order:
        ts = int(time.time() * 1000)
        return Order(
            id=str(uuid.uuid4()),
            parent_id=self.parent_order.id,
            client_order_id=f"swarm-{self.parent_order.id}-{index}-{uuid.uuid4().hex[:8]}",
            symbol=self.parent_order.symbol,
            side=self.parent_order.side,
            order_type=OrderType.LIMIT,
            price=price,
            amount=qty,
            remaining=qty,
            status=OrderStatus.PENDING,
            time_in_force=TimeInForce.GTC,
            timestamp=ts,
            last_update_timestamp=ts,
        )

    def record_fill(self, filled_qty: Decimal, fill_price: Decimal) -> None:
        if filled_qty <= 0:
            logger.warning(
                "swarm.invalid_fill",
                parent_id=self.parent_order.id,
                qty=str(filled_qty),
            )
            return

        self._fills.append({"qty": filled_qty, "price": fill_price})
        self._total_filled += filled_qty
        self._total_cost += filled_qty * fill_price
        self.parent_order.filled_amount += filled_qty

        logger.info(
            "swarm.fill",
            parent_id=self.parent_order.id,
            qty=str(filled_qty),
            price=str(fill_price),
            total_filled=str(self._total_filled),
            weighted_avg_price=str(self.get_weighted_avg_price()),
        )

    def get_weighted_avg_price(self) -> Decimal | None:
        """Volume-weighted average entry across all recorded fills."""
        if self._total_filled == 0:
            return None
        return self._total_cost / self._total_filled

    def _fill_percent(self) -> Decimal:
        if self.parent_order.total_amount <= 0:
            return Decimal("0")
        return self._total_filled / self.parent_order.total_amount * Decimal("100")

    def get_execution_summary(self) -> dict[str, Any]:
        """Snapshot of execution state for audit and post-trade analysis."""
        if self.plan is None:
            return {
                "status": "not_started",
                "parent_id": self.parent_order.id,
                "total_amount": str(self.parent_order.total_amount),
            }

        fill_percent = self._fill_percent()
        is_complete = self._total_filled >= self.parent_order.total_amount
        meets_threshold = is_complete or fill_percent >= self.min_fill_percent
        is_partial = self._total_filled > 0 and not is_complete and not meets_threshold

        if is_complete:
            status = "complete"
        elif is_partial:
            status = "partial"
        else:
            status = "executing"

        weighted_avg = self.get_weighted_avg_price()
        summary: dict[str, Any] = {
            "status": status,
            "parent_id": self.parent_order.id,
            "symbol": self.parent_order.symbol,
            "side": self.parent_order.side.value,
            "total_amount": str(self.parent_order.total_amount),
            "filled_amount": str(self._total_filled),
            "fill_percent": f"{fill_percent:.2f}%",
            "num_orders_planned": self.plan.num_orders,
            "num_fills": len(self._fills),
            "weighted_avg_price": (
                str(weighted_avg) if weighted_avg is not None else None
            ),
            "total_cost": str(self._total_cost),
            "min_fill_threshold": f"{self.min_fill_percent}%",
            "meets_threshold": meets_threshold,
        }

        if is_partial:
            summary["warning"] = (
                f"Partial fill: {fill_percent:.2f}% "
                f"(threshold {self.min_fill_percent}%)"
            )
            logger.warning(
                "swarm.partial_fill",
                parent_id=self.parent_order.id,
                fill_percent=f"{fill_percent:.2f}%",
                threshold=f"{self.min_fill_percent}%",
            )
        return summary

    def should_attach_stop_loss(self) -> bool:
        """True once enough of the parent has filled to protect a position."""
        if self._total_filled == 0:
            return False
        return self._fill_percent() >= self.min_fill_percent

    def get_stop_loss_order(self, stop_loss_pct: Decimal) -> Order | None:
        """Build a stop-market to protect the realised position.

        The stop is keyed off the weighted average entry rather than any single
        fill, and sized to the quantity actually filled. Returns ``None`` if the
        fill threshold has not been met.
        """
        if not self.should_attach_stop_loss():
            logger.info(
                "swarm.stop_skipped",
                parent_id=self.parent_order.id,
                filled=str(self._total_filled),
                target=str(self.parent_order.total_amount),
                reason="fill threshold not met",
            )
            return None

        weighted_avg = self.get_weighted_avg_price()
        if weighted_avg is None:
            return None

        if self.parent_order.side == OrderSide.BUY:
            sl_price = weighted_avg * (Decimal("1") - stop_loss_pct / Decimal("100"))
            sl_side = OrderSide.SELL
        else:
            sl_price = weighted_avg * (Decimal("1") + stop_loss_pct / Decimal("100"))
            sl_side = OrderSide.BUY

        ts = int(time.time() * 1000)
        sl_order = Order(
            id=str(uuid.uuid4()),
            parent_id=self.parent_order.id,
            client_order_id=f"sl-{self.parent_order.id}-{uuid.uuid4().hex[:8]}",
            symbol=self.parent_order.symbol,
            side=sl_side,
            order_type=OrderType.STOP_MARKET,
            price=sl_price,
            amount=self._total_filled,
            remaining=self._total_filled,
            status=OrderStatus.PENDING,
            time_in_force=TimeInForce.GTC,
            timestamp=ts,
            last_update_timestamp=ts,
        )
        logger.info(
            "swarm.stop_prepared",
            parent_id=self.parent_order.id,
            sl_order_id=sl_order.id,
            side=sl_side.value,
            weighted_avg_entry=str(weighted_avg),
            sl_price=str(sl_price),
            size=str(self._total_filled),
        )
        return sl_order
