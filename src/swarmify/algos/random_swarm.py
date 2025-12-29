"""
Random Swarm Order Algorithm - Execution Phase.
Follows pre-computed plan from SwarmPlanner.
"""

import uuid
import time
import asyncio
from decimal import Decimal
from typing import AsyncGenerator, List, Dict, Optional, Any
import structlog

from .base import ExecutionAlgo
from .swarm_planner import SwarmConfig, SwarmPlanner, SwarmPlan
from ..core.models import Order, AlgoOrder, Trade
from ..core.types import OrderType, OrderStatus, TimeInForce, OrderSide

logger = structlog.get_logger()


class RandomSwarmAlgo(ExecutionAlgo):
    """
    Random Swarm Order Algorithm - Production-grade implementation.

    Uses strategic randomness across three dimensions:
    1. Number of child orders (random between min/max)
    2. Quantity per order (random split of total)
    3. Timing between orders (random delays)

    This maximizes stealth and avoids detection patterns.

    Features:
    - Two-phase execution (planning → execution)
    - Weighted average entry price calculation
    - Partial fill tracking and validation
    - Stop-loss attachment after swarm completion
    - Comprehensive audit trail logging
    """

    def __init__(
        self,
        algo_order: AlgoOrder,
        config: Optional[SwarmConfig] = None,
        min_fill_percent: Decimal = Decimal("95.0"),
    ):
        super().__init__(algo_order)
        self.config = config or SwarmConfig()
        self.plan: Optional[SwarmPlan] = None
        self._plan_generated = False

        # Track fills for weighted average price calculation
        self._fills: List[Dict[str, Decimal]] = []  # [{"qty": ..., "price": ...}]
        self._total_filled = Decimal("0")
        self._total_cost = Decimal("0")

        # Partial fill detection
        self.min_fill_percent = min_fill_percent

    async def next_slice(
        self, current_market_price: Decimal
    ) -> AsyncGenerator[Order, None]:
        """
        Phase 2: Execution - Yield child orders according to pre-computed plan.
        """
        # Generate plan once on first call
        if not self._plan_generated:
            logger.info(
                "SWARM_START - Beginning swarm execution",
                parent_id=self.parent_order.id,
                symbol=self.parent_order.symbol,
                side=self.parent_order.side.value,
                total_amount=str(self.parent_order.total_amount),
                estimated_price=str(current_market_price),
            )

            self.plan = SwarmPlanner.create_plan(
                total_amount=self.parent_order.total_amount,
                estimated_price=current_market_price,
                config=self.config,
            )

            logger.info(
                "SWARM_PARTS_PREPARED - Execution plan ready",
                parent_id=self.parent_order.id,
                num_orders=self.plan.num_orders,
                quantities=[str(q) for q in self.plan.quantities],
                delays_ms=self.plan.delays_ms,
                min_delay_ms=self.config.min_delay_ms,
                max_delay_ms=self.config.max_delay_ms,
            )

            self._plan_generated = True

        # Execute according to plan
        filled_so_far = self.parent_order.filled_amount
        remaining = self.parent_order.total_amount - filled_so_far

        if remaining <= 0:
            logger.info(
                "SWARM_COMPLETE - All orders filled",
                parent_id=self.parent_order.id,
                total_filled=str(filled_so_far),
            )
            return

        # Determine which orders to yield this iteration
        # In a sequential model, we yield one at a time
        # The delays are handled by the caller between invocations

        for i, qty in enumerate(self.plan.quantities):
            # Check if this order has already been executed
            if filled_so_far >= sum(self.plan.quantities[: i + 1], Decimal("0")):
                continue  # Already filled

            # Apply delay before this order (except first)
            if i > 0 and i - 1 < len(self.plan.delays_ms):
                delay_sec = self.plan.delays_ms[i - 1] / 1000.0
                logger.info(
                    "SWARM_DELAY - Waiting between orders",
                    parent_id=self.parent_order.id,
                    slice_number=i + 1,
                    total_slices=self.plan.num_orders,
                    delay_ms=self.plan.delays_ms[i - 1],
                    delay_sec=f"{delay_sec:.3f}",
                )
                await asyncio.sleep(delay_sec)

            # Generate child order
            child = Order(
                id=str(uuid.uuid4()),
                parent_id=self.parent_order.id,
                client_order_id=f"swarm-{self.parent_order.id}-{i}-{uuid.uuid4().hex[:8]}",
                exchange_order_id=None,
                symbol=self.parent_order.symbol,
                side=self.parent_order.side,
                order_type=OrderType.LIMIT,
                price=current_market_price,  # Passive at current price
                amount=qty,
                remaining=qty,
                timestamp=int(time.time() * 1000),
                last_update_timestamp=int(time.time() * 1000),
                status=OrderStatus.PENDING,
                time_in_force=TimeInForce.GTC,
            )

            logger.info(
                "SWARM_ORDER_SUBMIT - Submitting child order",
                parent_id=self.parent_order.id,
                child_id=child.id,
                slice_number=f"{i + 1}/{self.plan.num_orders}",
                amount=str(qty),
                price=str(current_market_price),
                cumulative_qty=str(sum(self.plan.quantities[: i + 1], Decimal("0"))),
            )

            yield child

    def record_fill(self, filled_qty: Decimal, fill_price: Decimal) -> None:
        """
        Record a fill event for weighted average price calculation.

        Args:
            filled_qty: Quantity filled in this event
            fill_price: Price at which the fill occurred
        """
        if filled_qty <= 0:
            logger.warning(
                "swarm.invalid_fill",
                parent_id=self.parent_order.id,
                qty=str(filled_qty),
                msg="Attempted to record fill with non-positive quantity",
            )
            return

        self._fills.append({"qty": filled_qty, "price": fill_price})
        self._total_filled += filled_qty
        self._total_cost += filled_qty * fill_price

        logger.info(
            "swarm.fill_recorded",
            parent_id=self.parent_order.id,
            fill_qty=str(filled_qty),
            fill_price=str(fill_price),
            total_filled=str(self._total_filled),
            weighted_avg_price=str(self.get_weighted_avg_price()),
        )

    def get_weighted_avg_price(self) -> Optional[Decimal]:
        """
        Calculate weighted average entry price from all fills.

        Returns:
            Weighted average price, or None if no fills yet
        """
        if self._total_filled == 0:
            return None

        return self._total_cost / self._total_filled

    def get_execution_summary(self) -> Dict[str, Any]:
        """
        Generate comprehensive execution summary for audit trail.

        Returns:
            Dictionary containing execution metrics and status
        """
        if not self.plan:
            return {
                "status": "not_started",
                "parent_id": self.parent_order.id,
                "total_amount": str(self.parent_order.total_amount),
            }

        weighted_avg = self.get_weighted_avg_price()
        fill_percent = (
            (self._total_filled / self.parent_order.total_amount * Decimal("100"))
            if self.parent_order.total_amount > 0
            else Decimal("0")
        )

        is_complete = self._total_filled >= self.parent_order.total_amount
        has_partial_fill = (
            self._total_filled > 0
            and fill_percent < self.min_fill_percent
            and not is_complete
        )

        summary = {
            "status": (
                "complete"
                if is_complete
                else "partial" if has_partial_fill else "executing"
            ),
            "parent_id": self.parent_order.id,
            "symbol": self.parent_order.symbol,
            "side": self.parent_order.side.value,
            "total_amount": str(self.parent_order.total_amount),
            "filled_amount": str(self._total_filled),
            "fill_percent": f"{fill_percent:.2f}%",
            "num_orders_planned": self.plan.num_orders,
            "num_fills": len(self._fills),
            "weighted_avg_price": str(weighted_avg) if weighted_avg else None,
            "total_cost": str(self._total_cost),
            "min_fill_threshold": f"{self.min_fill_percent}%",
            "meets_threshold": fill_percent >= self.min_fill_percent or is_complete,
        }

        # Add warning if partial fill detected
        if has_partial_fill:
            summary["warning"] = (
                f"Partial fill detected: {fill_percent:.2f}% "
                f"(threshold: {self.min_fill_percent}%)"
            )
            logger.warning(
                "swarm.partial_fill_detected",
                parent_id=self.parent_order.id,
                fill_percent=f"{fill_percent:.2f}%",
                threshold=f"{self.min_fill_percent}%",
                filled=str(self._total_filled),
                target=str(self.parent_order.total_amount),
            )

        return summary

    def should_attach_stop_loss(self) -> bool:
        """
        Determine if stop-loss should be attached based on fill status.

        Returns:
            True if swarm is complete or meets minimum fill threshold
        """
        if self._total_filled == 0:
            return False

        fill_percent = (
            (self._total_filled / self.parent_order.total_amount * Decimal("100"))
            if self.parent_order.total_amount > 0
            else Decimal("0")
        )

        return fill_percent >= self.min_fill_percent

    def get_stop_loss_order(self, stop_loss_pct: Decimal) -> Optional[Order]:
        """
        Generate stop-loss order configuration after swarm completion.

        This method should be called after swarm execution completes.
        The returned order should be submitted through the OMS.

        Args:
            stop_loss_pct: Stop-loss percentage (e.g., 2.0 for 2%)

        Returns:
            Order object configured for stop-loss, or None if conditions not met
        """
        if not self.should_attach_stop_loss():
            logger.warning(
                "SWARM_SL_SKIP - Stop-loss conditions not met",
                parent_id=self.parent_order.id,
                filled=str(self._total_filled),
                target=str(self.parent_order.total_amount),
                reason="Insufficient fill percentage",
            )
            return None

        weighted_avg = self.get_weighted_avg_price()
        if not weighted_avg:
            logger.error(
                "SWARM_SL_ERROR - Cannot calculate stop-loss without weighted avg price",
                parent_id=self.parent_order.id,
            )
            return None

        # Calculate stop-loss price based on entry side
        if self.parent_order.side.value == "buy":
            # Long position - SL below entry
            sl_price = weighted_avg * (Decimal("1") - stop_loss_pct / Decimal("100"))
            sl_side = OrderSide.SELL
        else:
            # Short position - SL above entry
            sl_price = weighted_avg * (Decimal("1") + stop_loss_pct / Decimal("100"))
            sl_side = OrderSide.BUY

        sl_order = Order(
            id=str(uuid.uuid4()),
            parent_id=self.parent_order.id,
            client_order_id=f"sl-{self.parent_order.id}-{uuid.uuid4().hex[:8]}",
            exchange_order_id=None,
            symbol=self.parent_order.symbol,
            side=sl_side,
            order_type=OrderType.STOP_MARKET,
            price=sl_price,  # Stop trigger price
            amount=self._total_filled,  # Close entire position
            remaining=self._total_filled,
            timestamp=int(time.time() * 1000),
            last_update_timestamp=int(time.time() * 1000),
            status=OrderStatus.PENDING,
            time_in_force=TimeInForce.GTC,
        )

        logger.info(
            "SWARM_SL_PREPARED - Stop-loss order ready",
            parent_id=self.parent_order.id,
            sl_order_id=sl_order.id,
            entry_side=self.parent_order.side.value,
            sl_side=sl_side.value,
            weighted_avg_entry=str(weighted_avg),
            sl_price=str(sl_price),
            sl_pct=str(stop_loss_pct),
            position_size=str(self._total_filled),
        )

        return sl_order
