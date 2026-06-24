"""Iceberg execution: work a parent order in fixed-size slices."""

import time
import uuid
from collections.abc import AsyncGenerator
from decimal import Decimal

import structlog

from ..core.models import AlgoOrder, Order
from ..core.types import OrderStatus, OrderType, TimeInForce
from .base import ExecutionAlgo

logger = structlog.get_logger(__name__)


class IcebergAlgo(ExecutionAlgo):
    """Slice a parent order into equal child orders of ``slice_size``.

    The trailing slice carries whatever remainder is left, so the children
    always sum to the parent amount exactly.
    """

    name = "iceberg"

    def __init__(
        self,
        algo_order: AlgoOrder,
        slice_size: Decimal,
    ) -> None:
        super().__init__(algo_order)
        if slice_size <= 0:
            raise ValueError("slice_size must be > 0")
        self.slice_size = slice_size

    async def next_slice(self, current_market_price: Decimal) -> AsyncGenerator[Order]:
        remaining = self.parent_order.total_amount
        index = 0
        while remaining > 0:
            qty = min(self.slice_size, remaining)
            ts = int(time.time() * 1000)
            child = Order(
                id=str(uuid.uuid4()),
                parent_id=self.parent_order.id,
                client_order_id=f"ice-{self.parent_order.id}-{index}-{uuid.uuid4().hex[:8]}",
                symbol=self.parent_order.symbol,
                side=self.parent_order.side,
                order_type=OrderType.LIMIT,
                price=current_market_price,
                amount=qty,
                remaining=qty,
                status=OrderStatus.PENDING,
                time_in_force=TimeInForce.GTC,
                timestamp=ts,
                last_update_timestamp=ts,
            )
            logger.info(
                "iceberg.submit",
                parent_id=self.parent_order.id,
                child_id=child.id,
                amount=str(qty),
                price=str(current_market_price),
            )
            yield child
            remaining -= qty
            index += 1
