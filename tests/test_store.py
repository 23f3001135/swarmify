from decimal import Decimal

import pytest
import pytest_asyncio

from swarmify.core.models import Order
from swarmify.core.types import OrderSide, OrderStatus, OrderType
from swarmify.persistence.store import OrderStore

pytestmark = pytest.mark.asyncio


def _order(coid="c1", parent_id=None, status=OrderStatus.OPEN, ts=1) -> Order:
    return Order(
        id=coid,
        client_order_id=coid,
        parent_id=parent_id,
        exchange_order_id=f"ex-{coid}",
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        amount=Decimal("1.5"),
        price=Decimal("45000.12345678"),
        filled=Decimal("0.5"),
        status=status,
        timestamp=ts,
        last_update_timestamp=ts,
    )


@pytest_asyncio.fixture
async def store():
    s = OrderStore(":memory:")
    await s.connect()
    yield s
    await s.close()


async def test_round_trip_preserves_every_field(store):
    order = _order()
    await store.upsert(order)
    loaded = await store.get(order.id)

    assert loaded is not None
    for field in (
        "id",
        "client_order_id",
        "parent_id",
        "exchange_order_id",
        "symbol",
        "side",
        "order_type",
        "price",
        "amount",
        "filled",
        "remaining",
        "status",
        "time_in_force",
        "timestamp",
    ):
        assert getattr(loaded, field) == getattr(order, field)


async def test_upsert_updates_in_place(store):
    order = _order(status=OrderStatus.OPEN)
    await store.upsert(order)

    order.status = OrderStatus.FILLED
    order.filled = order.amount
    await store.upsert(order)

    loaded = await store.get(order.id)
    assert loaded.status == OrderStatus.FILLED
    assert loaded.filled == Decimal("1.5")


async def test_children_returned_in_timestamp_order(store):
    await store.upsert(_order(coid="b", parent_id="p", ts=20))
    await store.upsert(_order(coid="a", parent_id="p", ts=10))
    await store.upsert(_order(coid="other", parent_id="q", ts=15))

    children = await store.children_of("p")
    assert [c.client_order_id for c in children] == ["a", "b"]


async def test_get_missing_returns_none(store):
    assert await store.get("nope") is None


async def test_operations_before_connect_raise():
    s = OrderStore(":memory:")
    with pytest.raises(RuntimeError):
        await s.get("x")
