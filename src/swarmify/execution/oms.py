"""Order Management System: the single path orders take to the exchange.

The OMS owns the order lifecycle — risk approval, persistence, submission, and
state transitions — so that algorithms and the client never touch the exchange
directly. Submission is idempotent on ``client_order_id``.
"""

import time
from decimal import Decimal

import structlog

from ..core.models import Order
from ..core.types import OrderStatus
from ..exchange.base import BaseExchange
from ..persistence.store import OrderStore
from ..utils.metrics import Metrics
from .risk import RiskManager

logger = structlog.get_logger(__name__)


class OMS:
    def __init__(
        self,
        exchange: BaseExchange,
        risk: RiskManager | None = None,
        store: OrderStore | None = None,
        metrics: Metrics | None = None,
    ) -> None:
        self.exchange = exchange
        self.risk = risk or RiskManager()
        self.store = store
        self.metrics = metrics or Metrics()
        self._placed: dict[str, Order] = {}
        self._in_flight: set[str] = set()

    async def submit_order(
        self, order: Order, reference_price: Decimal | None = None
    ) -> Order:
        coid = order.client_order_id

        # Only an order we have actually placed counts as a duplicate. A prior
        # failed attempt must be allowed to retry, so we key the guard on the
        # placed set, not on "have we ever seen this id".
        placed = self._placed.get(coid)
        if placed is not None:
            logger.info("oms.duplicate", client_order_id=coid)
            return placed
        if coid in self._in_flight:
            raise RuntimeError(f"order {coid} is already in flight")

        decision = self.risk.check(order, reference_price)
        if not decision.approved:
            order.status = OrderStatus.REJECTED
            self.metrics.incr("orders.rejected")
            await self._persist(order)
            return order

        self._in_flight.add(coid)
        await self._persist(order)
        self.metrics.incr("orders.submitted")
        start = time.perf_counter()
        try:
            placed = await self.exchange.create_order(order)
        except Exception:
            self.metrics.incr("orders.errors")
            logger.exception("oms.submit_failed", client_order_id=coid)
            raise
        finally:
            self._in_flight.discard(coid)

        latency_ms = (time.perf_counter() - start) * 1000.0
        self.metrics.observe_latency("order_submit", latency_ms)
        placed.last_update_timestamp = int(time.time() * 1000)
        await self._persist(placed)
        self._placed[placed.client_order_id] = placed

        if placed.status == OrderStatus.FILLED:
            self.metrics.incr("orders.filled")
        logger.info(
            "oms.submitted",
            client_order_id=placed.client_order_id,
            exchange_order_id=placed.exchange_order_id,
            status=placed.status.value,
            latency_ms=round(latency_ms, 2),
        )
        return placed

    async def cancel_order(self, order: Order) -> Order:
        if order.is_terminal:
            logger.info(
                "oms.cancel_skipped",
                client_order_id=order.client_order_id,
                reason=f"already {order.status.value}",
            )
            return order

        if order.exchange_order_id is None:
            logger.warning(
                "oms.cancel_skipped",
                client_order_id=order.client_order_id,
                reason="no exchange_order_id",
            )
            return order

        await self.exchange.cancel_order(order.symbol, order.exchange_order_id)
        order.status = OrderStatus.CANCELED
        order.last_update_timestamp = int(time.time() * 1000)
        self.metrics.incr("orders.canceled")
        await self._persist(order)
        logger.info("oms.canceled", client_order_id=order.client_order_id)
        return order

    async def _persist(self, order: Order) -> None:
        if self.store is not None:
            await self.store.upsert(order)
