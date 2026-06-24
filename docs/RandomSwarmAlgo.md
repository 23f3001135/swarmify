# Random swarm

The random swarm works a parent order as a stream of child orders whose count,
sizes and timing are all randomised. The goal is execution that does not leave a
single recognisable footprint: no fixed slice size, no fixed cadence, no fixed
number of clips.

## Two stages

Planning is pure and synchronous; execution is async and does the I/O. Keeping
them apart makes the randomisation unit-testable and lets a caller inspect — or
reject — a plan before any order is sent.

```python
from decimal import Decimal
from swarmify.algos.swarm_planner import SwarmConfig, SwarmPlanner

plan = SwarmPlanner.create_plan(
    total_amount=Decimal("1.0"),
    estimated_price=Decimal("45000"),
    config=SwarmConfig(min_child_orders=3, max_child_orders=8),
)
# plan.num_orders, plan.quantities, plan.delays_ms
```

`create_plan`:

1. Derives the smallest acceptable child as `max(min_quantity, min_notional / price)`.
2. Caps the child count at what that floor allows, then draws a count in
   `[min_child_orders, max_child_orders]`.
3. Gives every child the floor, then partitions the surplus at random cut
   points. The final child absorbs the rounding residual, so the children sum to
   the parent exactly and none drops below the floor.
4. Draws `num_orders - 1` delays in `[min_delay_ms, max_delay_ms]`.

Pass `seed` in the config (or an explicit `rng`) for reproducible plans.

## Execution and fills

`next_slice` replays the plan, sleeping the planned delay before each child and
yielding it. The caller submits each child and reports fills back:

```python
algo = RandomSwarmAlgo(parent, config, min_fill_percent=Decimal("95"))
async for child in algo.next_slice(price):
    placed = await client.submit_order(child, reference_price=price)
    algo.record_fill(placed.filled, placed.average_price)
```

From the recorded fills the algorithm exposes:

- `get_weighted_avg_price()` — volume-weighted entry, or `None` before any fill.
- `get_execution_summary()` — status (`not_started` / `executing` / `partial` /
  `complete`), fill percent, weighted average, and a warning when the fill is
  below `min_fill_percent`.
- `should_attach_stop_loss()` — true once the fill clears the threshold.
- `get_stop_loss_order(pct)` — a stop-market sized to the filled quantity,
  priced `pct` away from the weighted-average entry (below for longs, above for
  shorts). Returns `None` if the threshold is not met.

## Configuration

See the table in the [README](../README.md#swarm-configuration). The constraint
that matters most in practice is the size/notional floor: it bounds how finely a
given parent can be split, and the planner silently reduces the child count
rather than emitting a child the venue would reject.
