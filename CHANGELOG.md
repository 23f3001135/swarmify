# Swarmify - Change Log

## Version 0.3.0 - Production-Grade Random Swarm (2025-12-27)

### 🚀 Major Enhancements: Battle-Tested Production Features

Enhanced **RandomSwarmAlgo** with production-grade patterns from institutional HFT systems:

**New Features:**

1. **Weighted Average Entry Price Calculation**
   - Automatically tracks all fill events (quantity + price)
   - Calculates weighted average entry for accurate P&L
   - Essential for position management and reporting
   - Method: `get_weighted_avg_price()`

2. **Partial Fill Detection & Validation**
   - Tracks fill percentage against target (default 95% threshold)
   - Warns if execution incomplete to prevent trading on partial positions
   - Prevents stop-loss attachment on insufficient fills
   - Configurable threshold: `min_fill_percent` parameter

3. **Automatic Stop-Loss Generation**
   - Generates SL order after swarm completes
   - Calculates SL price based on weighted avg entry (not first/last fill)
   - Handles LONG (SL below) and SHORT (SL above) positions
   - Configurable SL distance: `stop_loss_pct` parameter
   - Method: `get_stop_loss_order(stop_loss_pct)`

4. **Comprehensive Execution Summary**
   - Full audit trail for compliance and analysis
   - Includes: status, fill rate, weighted avg, total cost, warnings
   - Method: `get_execution_summary()`
   - Returns detailed dictionary with all metrics

5. **Enhanced Structured Logging**
   - Production-grade log prefixes for easy filtering:
     - `SWARM_START` - Execution begins
     - `SWARM_PARTS_PREPARED` - Plan ready with details
     - `SWARM_ORDER_SUBMIT` - Child order submitted
     - `SWARM_DELAY` - Waiting between orders
     - `SWARM_COMPLETE` - All orders filled
     - `SWARM_SL_PREPARED` - Stop-loss ready
     - `SWARM_SL_SKIP` - SL conditions not met
   - All logs include parent_id for traceability

**API Changes:**

```python
# Enhanced constructor with fill threshold
algo = RandomSwarmAlgo(
    algo_order=algo_order,
    config=config,
    min_fill_percent=Decimal("95.0")  # NEW: partial fill threshold
)

# NEW: Record fills as they occur
algo.record_fill(filled_qty=Decimal("0.1"), fill_price=Decimal("45000.0"))

# NEW: Get weighted average entry
weighted_avg = algo.get_weighted_avg_price()  # Returns Decimal or None

# NEW: Check if SL should be attached
if algo.should_attach_stop_loss():  # Respects fill threshold
    # NEW: Generate SL order
    sl_order = algo.get_stop_loss_order(stop_loss_pct=Decimal("2.0"))
    await client.oms.submit_order(sl_order)

# NEW: Get comprehensive summary
summary = algo.get_execution_summary()
# Returns: status, fill_percent, weighted_avg_price, warning (if partial), etc.
```

**Documentation:**
- Added comprehensive guide: `docs/RandomSwarmAlgo.md`
- Added production example: `examples/random_swarm_example.py`
- Updated README with new features and examples

**Exports:**
- Added `RandomSwarmAlgo` to public API (`__init__.py`)
- Added `SwarmConfig` to public API

**Tests:**
- All 15 tests passing (including 9 swarm-specific tests)
- Zero test failures, comprehensive coverage

---

## Version 0.2.0 - Random Swarm Order (2025-12-26)

### 🎯 Major Feature: Random Swarm Order Algorithm

Implemented advanced **Random Swarm Order** execution strategy for maximum stealth:

**Three Dimensions of Randomness:**
1. **Order Count**: Randomly splits into N child orders (configurable min/max)
2. **Quantity Distribution**: Random split of total amount respecting exchange minimums
3. **Timing Delays**: Random delays between orders (configurable range)

**Architecture:**
- **Phase 1 (Planning)**: Ultra-fast pre-computation using standard library
- **Phase 2 (Execution)**: Sequential placement following the randomized plan

**Key Components:**
- `SwarmPlanner`: Optimized planning with constraint validation
- `SwarmConfig`: Flexible configuration with sensible defaults
- `RandomSwarmAlgo`: Execution algorithm implementing the plan
- 9 comprehensive unit tests covering all edge cases

**Performance:**
- Planning phase: < 1ms for typical order counts
- Uses inline operations and standard library for speed
- Pre-validates all constraints before execution

**Safety:**
- Respects exchange minimum notional ($5 default)
- Respects exchange minimum quantity (0.001 default)
- Validates plan integrity before execution
- Full audit trail with logged execution plans

**Usage:**
```python
await client.execute_algo_order(
    symbol="BTC/USDT",
    side="buy",
    amount=10.0,
    algo="random_swarm",
    algo_params={
        "min_child_orders": 5,
        "max_child_orders": 15,
        "min_delay_ms": 200,
        "max_delay_ms": 3000
    }
)
```

See [docs/RANDOM_SWARM.md](docs/RANDOM_SWARM.md) for full technical documentation.

---

## Version 0.1.0 - Production Hardening (2025-12-26)

### 🔴 Critical Fixes

1. **Fixed Missing Imports** - Added `Dict`, `List`, `Any` imports to `core/models.py`
2. **Fixed Infinite Loop** - Corrected execution loop in `client.py` that was causing indefinite hangs
3. **Added Task Exception Handling** - Background execution tasks now properly propagate exceptions
4. **Fixed Type Signatures** - Corrected `AsyncGenerator` return types in algo base class
5. **Added Parent-Child Order Tracking** - Schema now includes `parent_id` for audit trail
6. **Fixed Null Pointer** - Added null check for `exchange_order_id` before cancellation

### 🟠 High Priority Improvements

7. **Network Timeouts** - All exchange calls now have 10-30s timeouts to prevent hangs
8. **Enhanced Idempotency** - Client order IDs now include UUID suffix to prevent collisions
9. **Market Order Risk Checks** - Risk manager now requires price estimates for market orders
10. **Connection Pooling** - SQLite now uses persistent connections with WAL mode
11. **Graceful Shutdown** - Properly cancels active tasks and closes connections
12. **Order Initialization** - `Order.remaining` field now correctly initialized

### 🟡 Medium Improvements

13. **Type Annotations** - Fixed type narrowing issues with `BaseExchange`
14. **Optional Parameters** - Corrected `Optional[Dict]` annotations
15. **Observability** - Added metrics tracking for latency, fill rate, rejection rate
16. **Public API** - Established stable import paths via `__init__.py` exports

### Testing

- Added 6 comprehensive test cases covering:
  - Risk management (limit & market orders)
  - OMS lifecycle (success & rejection paths)
  - Market order safety checks
  
All tests passing with `pytest -v`.

### API Changes

**Before:**
```python
from swarmify.execution.oms import OMS  # Deep import
```

**After:**
```python
from swarmify import SwarmClient, Order, OrderStatus  # Clean API
```

### Performance

- **Latency Tracking**: All orders now have end-to-end latency metrics
- **Database**: WAL mode enabled for concurrent reads during writes
- **Connection Reuse**: Eliminated per-operation connection overhead

### Safety

- Market orders without price estimates are rejected by default
- All exchange I/O operations have mandatory timeouts
- Background tasks are supervised and logged
- Graceful shutdown prevents orphaned orders

---

## Next Steps (Recommended)

1. **Add Circuit Breakers** - Auto-disable exchanges on repeated failures
2. **WebSocket Integration** - Real-time order updates instead of polling
3. **Position Tracking** - Net exposure limits across all symbols
4. **Reconciliation** - Recover in-flight orders on restart
5. **Retry Logic** - Exponential backoff with jitter for transient failures
6. **TWAP/VWAP Algos** - Time and volume weighted execution strategies
