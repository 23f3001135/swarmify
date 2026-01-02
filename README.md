# Swarmify Execution Engine

A high-performance, async algorithmic execution library for crypto trading, designed for hedge funds and HFT environments. Built on top of `ccxt` and `asyncio`.

> **Status**: Production-hardened after comprehensive code review. All critical bugs fixed, timeouts added, metrics instrumented.

## Features

*   **Exchange Abstraction**: Unified interface for Binance and Bybit (extensible to others).
*   **Algorithmic Execution**: 
    - **Iceberg**: Classic order slicing with fixed sizes
    - **Random Swarm** ⭐: Advanced stealth execution using randomness across timing, quantity, and order count
*   **Risk Management**: Pre-trade risk checks with market order price estimation and value limits.
*   **Precision**: Uses `decimal.Decimal` for all financial calculations to ensure zero floating-point errors.
*   **Persistence**: Async SQLite storage with WAL mode for robust order state management and audit trails.
*   **Type Safety**: Fully typed with `mypy` strict mode and Pydantic models.
*   **Observability**: Built-in metrics tracking for latency, fill rates, and rejection reasons.
*   **Production-Ready**: Timeouts on all I/O, graceful shutdown, exception handling, connection pooling.

## Algorithms

### Random Swarm Order ⭐ NEW: Production-Grade Features

The **Random Swarm** algorithm uses strategic randomness to maximize stealth when executing large orders:

**Three Dimensions of Randomness:**
1. **Order Count**: Randomly selects N child orders between `min_child_orders` and `max_child_orders`
2. **Quantity Split**: Randomly distributes total amount across N orders (respecting exchange minimums)
3. **Timing**: Random delays between each order (between `min_delay_ms` and `max_delay_ms`)

**Two-Phase Execution:**
- **Phase 1 (Planning)**: Pre-computes all randomization using optimized standard library operations
- **Phase 2 (Execution)**: Sequentially places orders according to the plan

**Production Features:**
- ✅ **Weighted Average Entry Price**: Automatically calculated from all fills for accurate P&L
- ✅ **Partial Fill Detection**: Warns if fill rate < 95% threshold
- ✅ **Stop-Loss Attachment**: Automatically generates SL order after swarm completes
- ✅ **Comprehensive Audit Trail**: Structured logging (SWARM_START, SWARM_PARTS_PREPARED, etc.)
- ✅ **Fill Tracking**: Records every fill event with price and quantity for analysis

This approach prevents pattern detection and minimizes market impact for institutional-sized orders.

**Documentation**: See [docs/RandomSwarmAlgo.md](docs/RandomSwarmAlgo.md) for detailed usage.

## Compatibility

*   **Python**: 3.13+ (leveraging latest `asyncio` and typing features)
*   **Exchanges**: 
    - ✅ **Binance** (Spot & Futures)
    - ✅ **Bybit** (Spot & Futures)
    - 🚧 **OKX** (Planned)
*   **OS**: Linux (Optimized for low-latency kernels), macOS, Windows.

## Installation

This project uses `uv` for dependency management.

```bash
uv sync
```

## Usage

Swarmify is designed to be imported as a library into your trading strategy codebase.

### Example: Random Swarm Order with Production Features

```python
import asyncio
from decimal import Decimal
from swarmify import SwarmClient, AlgoOrder, OrderSide, RandomSwarmAlgo, SwarmConfig

async def main():
    async with SwarmClient(
        api_key="YOUR_KEY", 
        secret="YOUR_SECRET", 
        exchange_name="binance",
        sandbox=True
    ) as client:
        
        # Configure swarm with production parameters
        config = SwarmConfig(
            min_child_orders=5,
            max_child_orders=15,
            min_delay_ms=500,
            max_delay_ms=3000,
            min_notional_usd=Decimal("100.0"),
            min_quantity=Decimal("0.001")
        )
        
        # Create algo order
        algo_order = AlgoOrder(
            id="swarm-001",
            client_order_id="swarm-001",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            total_amount=Decimal("2.0"),
            algo_name="random_swarm",
        )
        
        # Execute with 95% minimum fill threshold
        algo = RandomSwarmAlgo(
            algo_order=algo_order,
            config=config,
            min_fill_percent=Decimal("95.0")
        )
        
        # Execute swarm
        current_price = await client.get_ticker("BTC/USDT")
        async for child_order in algo.next_slice(current_price.last):
            await client.oms.submit_order(child_order)
            # Record fills as they occur
            # algo.record_fill(filled_qty, fill_price)
        
        # Get execution summary
        summary = algo.get_execution_summary()
        print(f"Status: {summary['status']}")
        print(f"Fill Rate: {summary['fill_percent']}")
        print(f"Weighted Avg Entry: ${summary['weighted_avg_price']}")
        
        # Attach stop-loss if conditions met (2% stop)
        if algo.should_attach_stop_loss():
            sl_order = algo.get_stop_loss_order(Decimal("2.0"))
            await client.oms.submit_order(sl_order)
            print(f"Stop-Loss attached at ${sl_order.price}")

if __name__ == "__main__":
    asyncio.run(main())
```

### Example: Iceberg Order

```python
# Classic iceberg with fixed slice size
parent_id = await client.execute_algo_order(
    symbol="BTC/USDT",
    side="buy",
    amount=10.0,
    algo="iceberg",
    algo_params={"slice_size": 0.5}  # Fixed 0.5 BTC slices
)
```

## Architecture

*   **Client (`swarmify.SwarmClient`)**: The main entry point. Manages the connection and spawns background execution tasks.
*   **OMS (`swarmify.execution.OMS`)**: Order Management System. Handles state transitions, idempotency, and persistence.
*   **Risk (`swarmify.execution.RiskManager`)**: The Gatekeeper. Rejects orders that violate safety limits, including market order estimation.
*   **Algos (`swarmify.algos`)**: 
    - `IcebergAlgo`: Fixed-size order slicing
    - `RandomSwarmAlgo`: Strategic randomization for stealth
*   **Metrics (`swarmify.utils.metrics`)**: Tracks order latency, fill rates, and rejection reasons for observability.

## Random Swarm Parameters

All parameters are **optional** with sensible defaults:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `min_child_orders` | 2 | Minimum number of child orders |
| `max_child_orders` | 10 | Maximum number of child orders |
| `min_delay_ms` | 0 | Minimum delay between orders (ms) |
| `max_delay_ms` | 1000 | Maximum delay between orders (ms) |
| `min_notional_usd` | 5.0 | Exchange minimum notional value |
| `min_quantity` | 0.001 | Exchange minimum quantity |

## Safety Features

1. **Network Timeouts**: All exchange calls have mandatory 10-30s timeouts
2. **Market Order Protection**: Requires price estimates; rejects if value exceeds limits
3. **Graceful Shutdown**: Cancels active tasks and prevents orphaned orders
4. **Audit Trail**: Parent-child order linkage persisted to database
5. **Idempotency**: UUID-based client order IDs prevent duplicate submissions
6. **Constraint Validation**: Ensures all orders meet exchange minimums before execution

## Development

Run tests:
```bash
uv run pytest -v
```

Format code:
```bash
uvx black src
uvx ruff check src
```

Type check:
```bash
uv run mypy src --strict
```

## Testing

15 comprehensive test cases covering:
- Risk management (limit & market orders)
- OMS lifecycle (success & rejection paths)
- Market order safety checks

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
- Random Swarm planning and validation
- Quantity splitting algorithms
- Constraint enforcement

All tests passing. See [CHANGELOG.md](CHANGELOG.md) for details.

## License

Proprietary & Confidential.