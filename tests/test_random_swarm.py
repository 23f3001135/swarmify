"""Fill tracking, partial-fill handling and stop generation for RandomSwarmAlgo."""

from decimal import Decimal

import pytest

from swarmify.algos.random_swarm import RandomSwarmAlgo
from swarmify.algos.swarm_planner import SwarmConfig
from swarmify.core.models import AlgoOrder
from swarmify.core.types import OrderSide


@pytest.fixture
def swarm_config():
    # Pin the order count so the plan is deterministic, and drop delays so the
    # async iteration does not actually sleep.
    return SwarmConfig(min_child_orders=3, max_child_orders=3, max_delay_ms=0)


@pytest.fixture
def buy_algo_order():
    return AlgoOrder(
        id="test-swarm-001",
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        total_amount=Decimal("1.0"),
    )


@pytest.fixture
def sell_algo_order():
    return AlgoOrder(
        id="test-swarm-002",
        symbol="ETH/USDT",
        side=OrderSide.SELL,
        total_amount=Decimal("10.0"),
    )


def test_weighted_avg_price_calculation(buy_algo_order, swarm_config):
    """Test weighted average price calculation with multiple fills."""
    algo = RandomSwarmAlgo(buy_algo_order, swarm_config)

    # Record three fills at different prices
    algo.record_fill(Decimal("0.1"), Decimal("45000.0"))
    algo.record_fill(Decimal("0.2"), Decimal("45100.0"))
    algo.record_fill(Decimal("0.3"), Decimal("45050.0"))

    # Calculate expected weighted average
    # (0.1 * 45000 + 0.2 * 45100 + 0.3 * 45050) / 0.6
    # = (4500 + 9020 + 13515) / 0.6 = 27035 / 0.6 = 45058.333...
    expected = Decimal("45058.33333333333333333333333")

    weighted_avg = algo.get_weighted_avg_price()
    assert weighted_avg is not None
    assert abs(weighted_avg - expected) < Decimal("0.01")


def test_weighted_avg_price_no_fills(buy_algo_order, swarm_config):
    """Test weighted average price returns None when no fills."""
    algo = RandomSwarmAlgo(buy_algo_order, swarm_config)

    assert algo.get_weighted_avg_price() is None


def test_weighted_avg_price_single_fill(buy_algo_order, swarm_config):
    """Test weighted average price with single fill."""
    algo = RandomSwarmAlgo(buy_algo_order, swarm_config)

    algo.record_fill(Decimal("0.5"), Decimal("45000.0"))

    weighted_avg = algo.get_weighted_avg_price()
    assert weighted_avg == Decimal("45000.0")


def test_record_fill_invalid_quantity(buy_algo_order, swarm_config):
    """Test that recording fill with zero or negative quantity is rejected."""
    algo = RandomSwarmAlgo(buy_algo_order, swarm_config)

    # Record invalid fill
    algo.record_fill(Decimal("0"), Decimal("45000.0"))
    algo.record_fill(Decimal("-0.1"), Decimal("45000.0"))

    # Should not be recorded
    assert len(algo._fills) == 0
    assert algo._total_filled == Decimal("0")
    assert algo.get_weighted_avg_price() is None


def test_partial_fill_detection_below_threshold(buy_algo_order, swarm_config):
    """Test partial fill detection when fill rate < threshold."""
    algo = RandomSwarmAlgo(
        buy_algo_order, swarm_config, min_fill_percent=Decimal("95.0")
    )

    # Fill only 60% (0.6 out of 1.0)
    algo.record_fill(Decimal("0.6"), Decimal("45000.0"))

    summary = algo.get_execution_summary()

    # Without plan, status is "not_started"
    assert summary["status"] == "not_started"
    assert summary["total_amount"] == "1.0"


def test_partial_fill_detection_above_threshold(buy_algo_order, swarm_config):
    """Test partial fill detection when fill rate >= threshold."""
    algo = RandomSwarmAlgo(
        buy_algo_order, swarm_config, min_fill_percent=Decimal("95.0")
    )

    # Fill 96% (0.96 out of 1.0)
    algo.record_fill(Decimal("0.96"), Decimal("45000.0"))

    # Should meet threshold
    assert algo.should_attach_stop_loss() is True


def test_stop_loss_generation_long_position(buy_algo_order, swarm_config):
    """Test stop-loss order generation for long position (BUY)."""
    algo = RandomSwarmAlgo(
        buy_algo_order, swarm_config, min_fill_percent=Decimal("95.0")
    )

    # Record fills to meet threshold (100%)
    algo.record_fill(Decimal("0.3"), Decimal("45000.0"))
    algo.record_fill(Decimal("0.3"), Decimal("45100.0"))
    algo.record_fill(Decimal("0.4"), Decimal("45050.0"))

    # Weighted avg should be around 45055
    weighted_avg = algo.get_weighted_avg_price()
    assert weighted_avg is not None

    # Generate SL with 2% stop
    sl_order = algo.get_stop_loss_order(Decimal("2.0"))

    assert sl_order is not None
    assert sl_order.side == OrderSide.SELL  # Close long with sell
    assert sl_order.symbol == "BTC/USDT"
    assert sl_order.amount == Decimal("1.0")  # Full position

    # SL price should be 2% below weighted avg
    expected_sl = weighted_avg * Decimal("0.98")
    assert abs(sl_order.price - expected_sl) < Decimal("1.0")


def test_stop_loss_generation_short_position(sell_algo_order, swarm_config):
    """Test stop-loss order generation for short position (SELL)."""
    algo = RandomSwarmAlgo(
        sell_algo_order, swarm_config, min_fill_percent=Decimal("95.0")
    )

    # Record fills to meet threshold
    algo.record_fill(Decimal("10.0"), Decimal("3000.0"))

    weighted_avg = algo.get_weighted_avg_price()
    assert weighted_avg == Decimal("3000.0")

    # Generate SL with 2% stop
    sl_order = algo.get_stop_loss_order(Decimal("2.0"))

    assert sl_order is not None
    assert sl_order.side == OrderSide.BUY  # Close short with buy
    assert sl_order.symbol == "ETH/USDT"
    assert sl_order.amount == Decimal("10.0")

    # SL price should be 2% above weighted avg
    expected_sl = weighted_avg * Decimal("1.02")
    assert sl_order.price == expected_sl


def test_stop_loss_not_generated_insufficient_fills(buy_algo_order, swarm_config):
    """Test that SL is not generated when fill rate < threshold."""
    algo = RandomSwarmAlgo(
        buy_algo_order, swarm_config, min_fill_percent=Decimal("95.0")
    )

    # Fill only 50%
    algo.record_fill(Decimal("0.5"), Decimal("45000.0"))

    # Should not generate SL
    assert algo.should_attach_stop_loss() is False
    sl_order = algo.get_stop_loss_order(Decimal("2.0"))
    assert sl_order is None


def test_stop_loss_not_generated_no_fills(buy_algo_order, swarm_config):
    """Test that SL is not generated when no fills."""
    algo = RandomSwarmAlgo(buy_algo_order, swarm_config)

    assert algo.should_attach_stop_loss() is False
    sl_order = algo.get_stop_loss_order(Decimal("2.0"))
    assert sl_order is None


@pytest.mark.asyncio
async def test_execution_summary_not_started(buy_algo_order, swarm_config):
    """Test execution summary when execution hasn't started."""
    algo = RandomSwarmAlgo(buy_algo_order, swarm_config)

    summary = algo.get_execution_summary()

    assert summary["status"] == "not_started"
    assert summary["parent_id"] == "test-swarm-001"
    assert summary["total_amount"] == "1.0"


@pytest.mark.asyncio
async def test_execution_summary_complete(buy_algo_order, swarm_config):
    """Test execution summary after complete execution."""
    algo = RandomSwarmAlgo(buy_algo_order, swarm_config)

    # Generate plan first
    current_price = Decimal("45000.0")
    async for _ in algo.next_slice(current_price):
        pass  # Just generate plan

    # Record fills to complete
    algo.record_fill(Decimal("0.4"), Decimal("45000.0"))
    algo.record_fill(Decimal("0.3"), Decimal("45100.0"))
    algo.record_fill(Decimal("0.3"), Decimal("45050.0"))

    summary = algo.get_execution_summary()

    assert summary["status"] == "complete"
    assert summary["parent_id"] == "test-swarm-001"
    assert summary["symbol"] == "BTC/USDT"
    assert summary["side"] == "buy"
    assert summary["filled_amount"] == "1.0"
    assert "100.00%" in summary["fill_percent"]
    assert summary["num_orders_planned"] == 3
    assert summary["num_fills"] == 3
    assert summary["weighted_avg_price"] is not None
    assert summary["meets_threshold"] is True
    assert "warning" not in summary


@pytest.mark.asyncio
async def test_execution_summary_partial_fill(buy_algo_order, swarm_config):
    """Test execution summary with partial fill warning."""
    algo = RandomSwarmAlgo(
        buy_algo_order, swarm_config, min_fill_percent=Decimal("95.0")
    )

    # Generate plan
    current_price = Decimal("45000.0")
    async for _ in algo.next_slice(current_price):
        pass

    # Record partial fills (60%)
    algo.record_fill(Decimal("0.6"), Decimal("45000.0"))

    summary = algo.get_execution_summary()

    assert summary["status"] == "partial"  # Partial because < threshold
    assert "60.00%" in summary["fill_percent"]
    assert summary["meets_threshold"] is False
    assert "warning" in summary  # Should have warning


def test_fill_tracking_accuracy(buy_algo_order, swarm_config):
    """Test that fill tracking maintains accurate totals."""
    algo = RandomSwarmAlgo(buy_algo_order, swarm_config)

    fills = [
        (Decimal("0.123"), Decimal("45123.45")),
        (Decimal("0.456"), Decimal("45456.78")),
        (Decimal("0.789"), Decimal("45789.12")),
    ]

    for qty, price in fills:
        algo.record_fill(qty, price)

    # Verify totals
    expected_qty = sum(f[0] for f in fills)
    expected_cost = sum(f[0] * f[1] for f in fills)

    assert algo._total_filled == expected_qty
    assert algo._total_cost == expected_cost
    assert len(algo._fills) == 3


def test_min_fill_percent_configuration(buy_algo_order, swarm_config):
    """Test that min_fill_percent can be configured."""
    algo_95 = RandomSwarmAlgo(
        buy_algo_order, swarm_config, min_fill_percent=Decimal("95.0")
    )
    algo_90 = RandomSwarmAlgo(
        buy_algo_order, swarm_config, min_fill_percent=Decimal("90.0")
    )
    algo_100 = RandomSwarmAlgo(
        buy_algo_order, swarm_config, min_fill_percent=Decimal("100.0")
    )

    assert algo_95.min_fill_percent == Decimal("95.0")
    assert algo_90.min_fill_percent == Decimal("90.0")
    assert algo_100.min_fill_percent == Decimal("100.0")

    # Fill 92%
    for algo in [algo_95, algo_90, algo_100]:
        algo.record_fill(Decimal("0.92"), Decimal("45000.0"))

    # Check thresholds
    assert algo_95.should_attach_stop_loss() is False  # 92% < 95%
    assert algo_90.should_attach_stop_loss() is True  # 92% >= 90%
    assert algo_100.should_attach_stop_loss() is False  # 92% < 100%


def test_fill_exactly_at_threshold_attaches_stop(buy_algo_order, swarm_config):
    algo = RandomSwarmAlgo(buy_algo_order, swarm_config, min_fill_percent=Decimal("95"))
    algo.record_fill(Decimal("0.95"), Decimal("45000"))
    assert algo.should_attach_stop_loss() is True


@pytest.mark.asyncio
async def test_fill_above_threshold_but_incomplete_is_executing(
    buy_algo_order, swarm_config
):
    algo = RandomSwarmAlgo(buy_algo_order, swarm_config, min_fill_percent=Decimal("95"))
    async for _ in algo.next_slice(Decimal("45000")):
        pass
    algo.record_fill(Decimal("0.97"), Decimal("45000"))

    summary = algo.get_execution_summary()
    assert summary["status"] == "executing"
    assert summary["meets_threshold"] is True
    assert "warning" not in summary


@pytest.mark.asyncio
async def test_over_fill_is_reported_complete(buy_algo_order, swarm_config):
    algo = RandomSwarmAlgo(buy_algo_order, swarm_config)
    async for _ in algo.next_slice(Decimal("45000")):
        pass
    algo.record_fill(Decimal("1.2"), Decimal("45000"))  # slipped past the parent size

    summary = algo.get_execution_summary()
    assert summary["status"] == "complete"
    assert summary["meets_threshold"] is True


@pytest.mark.asyncio
async def test_zero_price_fill_keeps_a_zero_average_not_none(
    buy_algo_order, swarm_config
):
    algo = RandomSwarmAlgo(buy_algo_order, swarm_config)
    async for _ in algo.next_slice(Decimal("45000")):
        pass
    algo.record_fill(Decimal("0.5"), Decimal("0"))

    assert algo.get_weighted_avg_price() == Decimal("0")
    assert algo.get_execution_summary()["weighted_avg_price"] == "0"


@pytest.mark.asyncio
async def test_child_orders_sum_to_parent(buy_algo_order, swarm_config):
    algo = RandomSwarmAlgo(buy_algo_order, swarm_config)
    children = [child async for child in algo.next_slice(Decimal("45000"))]

    assert len(children) == algo.plan.num_orders == 3
    assert sum(c.amount for c in children) == buy_algo_order.total_amount
    assert all(c.parent_id == buy_algo_order.id for c in children)
    assert all(c.side == OrderSide.BUY for c in children)
