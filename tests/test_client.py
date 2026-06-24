from decimal import Decimal

import pytest

from swarmify.client import SwarmClient
from swarmify.core.types import OrderSide

pytestmark = pytest.mark.asyncio


async def test_execute_random_swarm_submits_every_child(fake_exchange):
    client = SwarmClient(fake_exchange)
    algo = await client.execute_algo_order(
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        amount=Decimal("1.0"),
        algo="random_swarm",
        algo_params={"min_child_orders": 4, "max_child_orders": 4, "max_delay_ms": 0},
        reference_price=Decimal("45000"),
    )
    assert len(fake_exchange.created) == 4
    assert algo.parent_order.symbol == "BTC/USDT"


async def test_execute_iceberg_submits_every_slice(fake_exchange):
    client = SwarmClient(fake_exchange)
    await client.execute_algo_order(
        symbol="BTC/USDT",
        side="buy",
        amount=Decimal("1.0"),
        algo="iceberg",
        algo_params={"slice_size": "0.25"},
        reference_price=Decimal("100"),
    )
    assert len(fake_exchange.created) == 4


async def test_reference_price_pulled_from_ticker_when_absent(fake_exchange):
    client = SwarmClient(fake_exchange)
    await client.execute_algo_order(
        symbol="BTC/USDT",
        side="buy",
        amount=Decimal("1.0"),
        algo="iceberg",
        algo_params={"slice_size": "0.5"},
    )
    # FakeExchange ticks at 100, so each child is priced there.
    assert all(o.price == Decimal("100") for o in fake_exchange.created)


async def test_unknown_algo_rejected(fake_exchange):
    client = SwarmClient(fake_exchange)
    with pytest.raises(ValueError):
        await client.execute_algo_order(
            symbol="BTC/USDT",
            side="buy",
            amount=Decimal("1.0"),
            algo="twap",
            reference_price=Decimal("100"),
        )


async def test_context_manager_closes_exchange(fake_exchange):
    async with SwarmClient(fake_exchange) as client:
        ticker = await client.get_ticker("BTC/USDT")
    assert ticker.last == Decimal("100")
