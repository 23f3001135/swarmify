from decimal import Decimal

import pytest
from pydantic import ValidationError

from swarmify.core.models import AlgoOrder, Order
from swarmify.core.types import OrderSide, OrderStatus, OrderType


def _order(**overrides) -> Order:
    base = dict(
        id="o1",
        client_order_id="c1",
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        amount=Decimal("2"),
    )
    base.update(overrides)
    return Order(**base)


def test_remaining_defaults_to_unfilled_amount():
    order = _order(filled=Decimal("0.5"))
    assert order.remaining == Decimal("1.5")


def test_explicit_remaining_is_kept():
    order = _order(remaining=Decimal("2"))
    assert order.remaining == Decimal("2")


def test_is_terminal_tracks_status():
    assert _order(status=OrderStatus.FILLED).is_terminal
    assert not _order(status=OrderStatus.OPEN).is_terminal


def test_order_rejects_unknown_field():
    with pytest.raises(ValidationError):
        _order(algo_type="oops")


def test_algo_order_remaining_amount():
    parent = AlgoOrder(
        id="a1",
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        total_amount=Decimal("5"),
        filled_amount=Decimal("2"),
    )
    assert parent.remaining_amount == Decimal("3")


def test_algo_order_rejects_unknown_field():
    with pytest.raises(ValidationError):
        AlgoOrder(
            id="a1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            total_amount=Decimal("1"),
            algo_type="random_swarm",
        )


@pytest.mark.parametrize("amount", ["0", "-1", "-0.0001"])
def test_order_rejects_non_positive_amount(amount):
    with pytest.raises(ValidationError):
        _order(amount=Decimal(amount))


@pytest.mark.parametrize("price", ["0", "-100"])
def test_order_rejects_non_positive_price(price):
    with pytest.raises(ValidationError):
        _order(price=Decimal(price))


def test_order_allows_no_price():
    assert _order(price=None).price is None


@pytest.mark.parametrize("total", ["0", "-5"])
def test_algo_order_rejects_non_positive_total(total):
    with pytest.raises(ValidationError):
        AlgoOrder(
            id="a1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            total_amount=Decimal(total),
        )
