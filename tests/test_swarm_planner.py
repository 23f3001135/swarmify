import random
from decimal import Decimal

import pytest

from swarmify.algos.swarm_planner import SwarmConfig, SwarmPlanner

PRICE = Decimal("45000")


def test_plan_count_within_bounds():
    config = SwarmConfig(min_child_orders=3, max_child_orders=8)
    plan = SwarmPlanner.create_plan(Decimal("2"), PRICE, config)
    assert 3 <= plan.num_orders <= 8
    assert len(plan.quantities) == plan.num_orders
    assert len(plan.delays_ms) == plan.num_orders - 1


def test_quantities_sum_exactly_to_total():
    config = SwarmConfig(min_child_orders=2, max_child_orders=9)
    total = Decimal("3.7")
    plan = SwarmPlanner.create_plan(total, PRICE, config)
    assert plan.total_quantity() == total


def test_every_child_meets_the_size_floor():
    config = SwarmConfig(
        min_child_orders=2, max_child_orders=6, min_quantity=Decimal("0.1")
    )
    plan = SwarmPlanner.create_plan(Decimal("1.0"), Decimal("100"), config)
    assert all(qty >= Decimal("0.1") for qty in plan.quantities)


def test_notional_floor_can_bind_instead_of_quantity_floor():
    # At a price of 1, the $5 notional floor implies a 5-unit minimum, which is
    # larger than the size floor and therefore the binding constraint.
    config = SwarmConfig(
        min_child_orders=2,
        max_child_orders=10,
        min_notional_usd=Decimal("5"),
        min_quantity=Decimal("0.001"),
    )
    plan = SwarmPlanner.create_plan(Decimal("20"), Decimal("1"), config)
    assert plan.num_orders <= 4
    assert all(qty >= Decimal("5") for qty in plan.quantities)


def test_delays_fall_within_configured_window():
    config = SwarmConfig(
        min_child_orders=4, max_child_orders=4, min_delay_ms=100, max_delay_ms=300
    )
    plan = SwarmPlanner.create_plan(Decimal("1.0"), PRICE, config)
    assert all(100 <= d <= 300 for d in plan.delays_ms)


def test_single_order_is_the_whole_parent():
    config = SwarmConfig(min_child_orders=1, max_child_orders=1)
    plan = SwarmPlanner.create_plan(Decimal("1.0"), PRICE, config)
    assert plan.num_orders == 1
    assert plan.quantities == [Decimal("1.0")]
    assert plan.delays_ms == []


def test_amount_below_minimum_raises():
    config = SwarmConfig(min_quantity=Decimal("0.001"))
    with pytest.raises(ValueError):
        SwarmPlanner.create_plan(Decimal("0.0005"), PRICE, config)


def test_order_count_capped_by_feasibility():
    # Only three children of >= 0.1 fit into 0.3, even though up to ten are asked.
    config = SwarmConfig(
        min_child_orders=10, max_child_orders=10, min_quantity=Decimal("0.1")
    )
    plan = SwarmPlanner.create_plan(Decimal("0.3"), Decimal("100"), config)
    assert plan.num_orders == 3


def test_same_seed_produces_identical_plan():
    config = SwarmConfig(min_child_orders=2, max_child_orders=9, seed=42)
    a = SwarmPlanner.create_plan(Decimal("2.0"), PRICE, config)
    b = SwarmPlanner.create_plan(Decimal("2.0"), PRICE, config)
    assert a == b


def test_non_positive_inputs_raise():
    config = SwarmConfig()
    with pytest.raises(ValueError):
        SwarmPlanner.create_plan(Decimal("0"), PRICE, config)
    with pytest.raises(ValueError):
        SwarmPlanner.create_plan(Decimal("1"), Decimal("0"), config)


def test_invalid_config_rejected():
    with pytest.raises(ValueError):
        SwarmConfig(min_child_orders=5, max_child_orders=2)
    with pytest.raises(ValueError):
        SwarmConfig(min_delay_ms=500, max_delay_ms=100)


# --- invariants that must hold for every plan, swept across many RNG draws ---

_CASES = [
    # (total, price, config)
    (
        Decimal("1.0"),
        Decimal("45000"),
        SwarmConfig(min_child_orders=2, max_child_orders=10),
    ),
    (
        Decimal("3.7"),
        Decimal("123.45"),
        SwarmConfig(min_child_orders=1, max_child_orders=9),
    ),
    (
        Decimal("0.05"),
        Decimal("60000"),
        SwarmConfig(min_child_orders=2, max_child_orders=8),
    ),
    (Decimal("20"), Decimal("1"), SwarmConfig(min_child_orders=3, max_child_orders=12)),
    (
        Decimal("100"),
        Decimal("0.5"),
        SwarmConfig(
            min_child_orders=4,
            max_child_orders=15,
            min_notional_usd=Decimal("10"),
            min_quantity=Decimal("0.5"),
        ),
    ),
    (
        Decimal("2.5"),
        Decimal("9999.99"),
        SwarmConfig(min_child_orders=5, max_child_orders=5),
    ),
]


def _min_order(price: Decimal, config: SwarmConfig) -> Decimal:
    return max(config.min_quantity, config.min_notional_usd / price)


@pytest.mark.parametrize("total,price,config", _CASES)
def test_invariants_hold_across_many_seeds(total, price, config):
    min_order = _min_order(price, config)
    feasible = int(total / min_order)

    for seed in range(250):
        plan = SwarmPlanner.create_plan(total, price, config, rng=random.Random(seed))

        # Structural shape.
        assert plan.num_orders == len(plan.quantities)
        assert len(plan.delays_ms) == plan.num_orders - 1
        assert 1 <= plan.num_orders <= config.max_child_orders
        assert plan.num_orders <= feasible

        # The whole parent is worked, to the last unit.
        assert plan.total_quantity() == total

        # No child the venue would reject, and no negative clip.
        assert all(qty >= min_order for qty in plan.quantities)

        # Delays stay inside the configured window.
        assert all(
            config.min_delay_ms <= d <= config.max_delay_ms for d in plan.delays_ms
        )


@pytest.mark.parametrize("total,price,config", _CASES)
def test_count_honours_lower_bound_when_feasible(total, price, config):
    feasible = int(total / _min_order(price, config))
    for seed in range(100):
        plan = SwarmPlanner.create_plan(total, price, config, rng=random.Random(seed))
        if feasible >= config.min_child_orders:
            assert plan.num_orders >= config.min_child_orders
        else:
            # Constraints do not allow the requested floor; clamp to feasible.
            assert plan.num_orders == feasible


def test_explicit_rng_makes_planning_reproducible():
    config = SwarmConfig(min_child_orders=2, max_child_orders=9)
    a = SwarmPlanner.create_plan(
        Decimal("4"), Decimal("250"), config, rng=random.Random(7)
    )
    b = SwarmPlanner.create_plan(
        Decimal("4"), Decimal("250"), config, rng=random.Random(7)
    )
    assert a == b
