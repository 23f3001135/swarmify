"""Pre-trade risk checks applied to every child order before it is sent."""

from dataclasses import dataclass
from decimal import Decimal

import structlog

from ..core.models import Order
from ..core.types import OrderType

logger = structlog.get_logger(__name__)

_MARKET_TYPES = (OrderType.MARKET, OrderType.STOP_MARKET)


@dataclass(frozen=True)
class RiskLimits:
    """Hard limits enforced per order. ``None`` disables the individual check."""

    max_order_notional_usd: Decimal | None = None
    max_order_quantity: Decimal | None = None
    reject_market_without_price: bool = True


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reason: str | None = None


class RiskManager:
    """Stateless gatekeeper that approves or rejects individual orders."""

    def __init__(self, limits: RiskLimits | None = None) -> None:
        self.limits = limits or RiskLimits()

    def check(
        self, order: Order, reference_price: Decimal | None = None
    ) -> RiskDecision:
        price = order.price or reference_price

        # A market order carries no price, so without an external estimate we
        # cannot bound its value. Refuse rather than fire blind.
        if order.order_type in _MARKET_TYPES and price is None:
            if self.limits.reject_market_without_price:
                return self._reject(order, "market order requires a reference price")
            return RiskDecision(True)

        if (
            self.limits.max_order_quantity is not None
            and order.amount > self.limits.max_order_quantity
        ):
            return self._reject(
                order,
                f"quantity {order.amount} exceeds limit "
                f"{self.limits.max_order_quantity}",
            )

        if self.limits.max_order_notional_usd is not None and price is not None:
            notional = price * order.amount
            if notional > self.limits.max_order_notional_usd:
                return self._reject(
                    order,
                    f"notional {notional} exceeds limit "
                    f"{self.limits.max_order_notional_usd}",
                )

        return RiskDecision(True)

    def _reject(self, order: Order, reason: str) -> RiskDecision:
        logger.warning(
            "risk.rejected",
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            reason=reason,
        )
        return RiskDecision(False, reason)
