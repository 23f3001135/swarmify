from decimal import Decimal

from swarmify.core.models import Order
from swarmify.core.types import OrderSide, OrderType
from swarmify.execution.risk import RiskLimits, RiskManager


def _order(order_type=OrderType.LIMIT, amount="1", price="100") -> Order:
    return Order(
        id="o1",
        client_order_id="c1",
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        order_type=order_type,
        amount=Decimal(amount),
        price=Decimal(price) if price is not None else None,
    )


def test_order_within_limits_is_approved():
    risk = RiskManager(
        RiskLimits(
            max_order_notional_usd=Decimal("1000"),
            max_order_quantity=Decimal("10"),
        )
    )
    assert risk.check(_order()).approved


def test_quantity_over_limit_is_rejected():
    risk = RiskManager(RiskLimits(max_order_quantity=Decimal("0.5")))
    decision = risk.check(_order(amount="1"))
    assert not decision.approved
    assert "quantity" in decision.reason


def test_notional_over_limit_is_rejected():
    risk = RiskManager(RiskLimits(max_order_notional_usd=Decimal("50")))
    decision = risk.check(_order(amount="1", price="100"))
    assert not decision.approved
    assert "notional" in decision.reason


def test_market_order_without_price_is_rejected():
    risk = RiskManager()
    decision = risk.check(_order(order_type=OrderType.MARKET, price=None))
    assert not decision.approved


def test_market_order_uses_reference_price():
    risk = RiskManager(RiskLimits(max_order_notional_usd=Decimal("50")))
    order = _order(order_type=OrderType.MARKET, amount="1", price=None)
    decision = risk.check(order, reference_price=Decimal("100"))
    assert not decision.approved
    assert "notional" in decision.reason


def test_no_limits_approves_everything():
    risk = RiskManager()
    assert risk.check(_order(amount="1000000", price="100000")).approved
