from decimal import Decimal

import pytest

from conftest import FakeExchange
from swarmify.core.models import Order
from swarmify.core.types import OrderSide, OrderStatus, OrderType
from swarmify.execution.oms import OMS
from swarmify.execution.risk import RiskLimits, RiskManager
from swarmify.persistence.store import OrderStore

pytestmark = pytest.mark.asyncio


def _order(client_order_id="c1", amount="1", price="100", parent_id=None) -> Order:
    return Order(
        id=client_order_id,
        client_order_id=client_order_id,
        parent_id=parent_id,
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        amount=Decimal(amount),
        price=Decimal(price),
    )


async def test_submit_fills_and_counts_metrics(fake_exchange):
    oms = OMS(fake_exchange)
    placed = await oms.submit_order(_order())

    assert placed.status == OrderStatus.FILLED
    assert placed.exchange_order_id == "ex-1"
    assert oms.metrics.counters["orders.submitted"] == 1
    assert oms.metrics.counters["orders.filled"] == 1
    assert oms.metrics.latencies["order_submit"].count == 1


async def test_risk_rejection_never_reaches_exchange(fake_exchange):
    risk = RiskManager(RiskLimits(max_order_quantity=Decimal("0.1")))
    oms = OMS(fake_exchange, risk=risk)

    placed = await oms.submit_order(_order(amount="1"))

    assert placed.status == OrderStatus.REJECTED
    assert fake_exchange.created == []
    assert oms.metrics.counters["orders.rejected"] == 1


async def test_submit_is_idempotent_on_client_order_id(fake_exchange):
    oms = OMS(fake_exchange)
    first = await oms.submit_order(_order(client_order_id="dup"))
    second = await oms.submit_order(_order(client_order_id="dup"))

    assert first is second
    assert len(fake_exchange.created) == 1


async def test_exchange_error_propagates_and_is_counted(fake_exchange):
    fake_exchange.fail_next = True
    oms = OMS(fake_exchange)

    with pytest.raises(RuntimeError):
        await oms.submit_order(_order())

    assert oms.metrics.counters["orders.errors"] == 1


async def test_cancel_marks_resting_order_canceled():
    exchange = FakeExchange(fill=False)
    oms = OMS(exchange)
    placed = await oms.submit_order(_order())
    assert placed.status == OrderStatus.OPEN

    canceled = await oms.cancel_order(placed)

    assert canceled.status == OrderStatus.CANCELED
    assert exchange.canceled == [("BTC/USDT", "ex-1")]


async def test_cancel_is_a_noop_on_a_terminal_order(fake_exchange):
    oms = OMS(fake_exchange)
    placed = await oms.submit_order(_order())  # FakeExchange fills immediately
    assert placed.status == OrderStatus.FILLED

    result = await oms.cancel_order(placed)

    assert result.status == OrderStatus.FILLED
    assert fake_exchange.canceled == []


async def test_retry_after_transient_failure_resubmits(fake_exchange):
    # A failed first attempt must not lock the client_order_id out of a retry.
    fake_exchange.fail_next = True
    oms = OMS(fake_exchange)

    with pytest.raises(RuntimeError):
        await oms.submit_order(_order(client_order_id="retry-me"))

    placed = await oms.submit_order(_order(client_order_id="retry-me"))

    assert placed.status == OrderStatus.FILLED
    assert len(fake_exchange.created) == 2
    assert oms.metrics.counters["orders.errors"] == 1


async def test_rejected_order_can_be_resubmitted_after_limits_change(fake_exchange):
    risk = RiskManager(RiskLimits(max_order_quantity=Decimal("0.5")))
    oms = OMS(fake_exchange, risk=risk)

    rejected = await oms.submit_order(_order(client_order_id="r1", amount="1"))
    assert rejected.status == OrderStatus.REJECTED

    # Operator widens the limit and resubmits the same id; it must go through.
    oms.risk = RiskManager(RiskLimits(max_order_quantity=Decimal("10")))
    placed = await oms.submit_order(_order(client_order_id="r1", amount="1"))
    assert placed.status == OrderStatus.FILLED


async def test_persistence_records_parent_child_links(fake_exchange):
    store = OrderStore(":memory:")
    await store.connect()
    try:
        oms = OMS(fake_exchange, store=store)
        await oms.submit_order(_order(client_order_id="child-1", parent_id="parent"))
        await oms.submit_order(_order(client_order_id="child-2", parent_id="parent"))

        children = await store.children_of("parent")
        assert {c.client_order_id for c in children} == {"child-1", "child-2"}
        assert all(c.status == OrderStatus.FILLED for c in children)
    finally:
        await store.close()
