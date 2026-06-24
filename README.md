# Swarmify

An async execution engine for crypto venues. Swarmify takes a parent order and
works it into the market as a stream of child orders — sliced, sized and timed
to keep a large order from showing up as a single recognisable print. It is a
library: you import it into a strategy, not a standalone bot.

Built on `ccxt`, `asyncio` and Pydantic. All sizes and prices are
`decimal.Decimal`, so rounding is explicit rather than whatever a float happens
to do.

## Layout

```
swarmify/
  core/         types and Pydantic models (Order, AlgoOrder, Ticker, ...)
  algos/        execution algorithms and the swarm planner
  exchange/     BaseExchange interface and the ccxt adapter
  execution/    RiskManager (pre-trade checks) and OMS (order lifecycle)
  persistence/  aiosqlite order store with a parent/child audit trail
  utils/        in-process metrics
  client.py     SwarmClient — wires the above together
```

## Algorithms

- **Iceberg** — fixed-size slices; the trailing slice carries the remainder.
- **Random swarm** — a random number of children, random sizes (each above the
  venue's size and notional floors) and random gaps between them. The plan is
  computed up front so it can be inspected before anything is sent; execution
  then replays it. The algorithm also tracks fills, reports a weighted-average
  entry, flags under-filled executions and can derive a protective stop from the
  realised entry.

## Install

```bash
uv sync
```

To use it from another project, add it as a dependency (`uv add swarmify` once
published, or a path/git reference during development).

## Usage

High-level: hand the client a parent order and let it pick and run the
algorithm. `execute_algo_order` returns the algorithm instance so you can read
fills, pull a summary, or attach a stop afterwards.

```python
import asyncio
from decimal import Decimal

from swarmify import SwarmClient, OrderSide


async def main():
    async with SwarmClient.for_exchange(
        "binance", "KEY", "SECRET", sandbox=True
    ) as client:
        algo = await client.execute_algo_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            amount=Decimal("2.0"),
            algo="random_swarm",
            algo_params={
                "min_child_orders": 5,
                "max_child_orders": 15,
                "min_delay_ms": 500,
                "max_delay_ms": 3000,
            },
        )

        summary = algo.get_execution_summary()
        print(summary["status"], summary["fill_percent"], summary["weighted_avg_price"])

        if algo.should_attach_stop_loss():
            stop = algo.get_stop_loss_order(Decimal("2.0"))
            await client.submit_order(stop)


asyncio.run(main())
```

Low-level: drive the algorithm yourself and submit each child through the OMS.

```python
from swarmify import AlgoOrder, RandomSwarmAlgo, SwarmConfig

parent = AlgoOrder(id="swarm-001", symbol="BTC/USDT", side=OrderSide.BUY,
                   total_amount=Decimal("2.0"))
algo = RandomSwarmAlgo(parent, config=SwarmConfig(min_child_orders=5))

price = (await client.get_ticker("BTC/USDT")).last
async for child in algo.next_slice(price):
    placed = await client.submit_order(child, reference_price=price)
    # feed fills back as the exchange reports them:
    # algo.record_fill(placed.filled, placed.average_price)
```

Iceberg is the same call with a slice size:

```python
await client.execute_algo_order(
    symbol="BTC/USDT", side="buy", amount=Decimal("10"),
    algo="iceberg", algo_params={"slice_size": "0.5"},
)
```

A runnable, offline walk-through lives in
[examples/random_swarm_example.py](examples/random_swarm_example.py).

## Swarm configuration

| Parameter          | Default | Meaning                                   |
|--------------------|---------|-------------------------------------------|
| `min_child_orders` | 2       | Lower bound on the child count            |
| `max_child_orders` | 10      | Upper bound on the child count            |
| `min_delay_ms`     | 0       | Minimum gap between children              |
| `max_delay_ms`     | 1000    | Maximum gap between children              |
| `min_notional_usd` | 5       | Venue minimum order value                 |
| `min_quantity`     | 0.001   | Venue minimum order size                  |
| `seed`             | None    | Fix the RNG for reproducible plans/tests  |

The planner clamps the child count to what the constraints allow: it never
produces a child below the size or notional floor, and the children always sum
to the parent amount exactly.

## Safety

- Every `ccxt` call is wrapped in a timeout.
- The risk manager runs before each child and refuses a market order it cannot
  price, or any order over the configured notional/quantity limits.
- Submission is idempotent on `client_order_id`.
- Parent/child links are persisted, so an execution can be reconstructed.

## Development

```bash
uv run pytest          # tests
uv run ruff check .    # lint
uv run black .         # format
uv run mypy            # type check
```
