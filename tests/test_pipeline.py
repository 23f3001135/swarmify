from decimal import Decimal

import pytest

from swarmify.client import SwarmClient
from swarmify.core.types import OrderSide, OrderStatus
from swarmify.execution.risk import RiskLimits, RiskManager
from swarmify.persistence.store import OrderStore

pytestmark = pytest.mark.asyncio

PARAMS = {"min_child_orders": 4, "max_child_orders": 4, "max_delay_ms": 0}


async def test_swarm_children_are_filled_and_persisted(fake_exchange):
    store = OrderStore(":memory:")
    async with SwarmClient(fake_exchange, store=store) as client:
        algo = await client.execute_algo_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            amount=Decimal("2.0"),
            algo="random_swarm",
            algo_params=PARAMS,
            reference_price=Decimal("45000"),
        )

        children = await store.children_of(algo.parent_order.id)

    assert len(children) == 4
    assert all(c.status == OrderStatus.FILLED for c in children)
    assert sum(c.amount for c in children) == Decimal("2.0")
    assert client.metrics.counters["orders.filled"] == 4


async def test_risk_blocks_oversized_children_before_the_exchange(fake_exchange):
    risk = RiskManager(RiskLimits(max_order_notional_usd=Decimal("1")))
    client = SwarmClient(fake_exchange, risk=risk)

    await client.execute_algo_order(
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        amount=Decimal("2.0"),
        algo="random_swarm",
        algo_params=PARAMS,
        reference_price=Decimal("45000"),
    )

    assert fake_exchange.created == []
    assert client.metrics.counters["orders.rejected"] == 4
    assert "orders.filled" not in client.metrics.counters
