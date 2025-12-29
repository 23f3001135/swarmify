# RandomSwarmAlgo - Production-Grade Swarm Execution

## Overview

The `RandomSwarmAlgo` implements a sophisticated order execution strategy that uses **three dimensions of randomness** to maximize stealth and avoid market impact detection:

1. **Order Count Randomization**: Number of child orders varies randomly between configured min/max
2. **Quantity Randomization**: Each order gets a random portion of the total (non-uniform distribution)
3. **Timing Randomization**: Random delays between orders to avoid predictable patterns

## Architecture: Two-Phase Execution

### Phase 1: Planning (Optimized for Speed)
```python
# Executed once at start, uses stdlib only for maximum performance
plan = SwarmPlanner.create_plan(
    total_amount=Decimal("1.0"),
    estimated_price=Decimal("45000.0"),
    config=SwarmConfig(...)
)
# Result: SwarmPlan with pre-computed quantities and delays
```

**Planning generates:**
- Random number of child orders (N)
- Random quantity splits that sum to total
- Random delays (N-1 delays for N orders)
- All constraints validated upfront

### Phase 2: Execution
```python
# Yields child orders according to plan
async for child_order in algo.next_slice(current_price):
    await oms.submit_order(child_order)
    # Track fills as they occur
    algo.record_fill(filled_qty, fill_price)
```

## Key Features

### 1. Weighted Average Entry Price
```python
# Automatically calculated from all fills
weighted_avg = algo.get_weighted_avg_price()
# Example: 3 fills at different prices
# Fill 1: 0.1 BTC @ $45,000
# Fill 2: 0.2 BTC @ $45,100  
# Fill 3: 0.3 BTC @ $45,050
# Weighted Avg = (0.1*45000 + 0.2*45100 + 0.3*45050) / 0.6 = $45,066.67
```

### 2. Partial Fill Detection
```python
# Warns if fill rate < threshold (default 95%)
summary = algo.get_execution_summary()
if summary['status'] == 'partial':
    # Log alert: only 60% filled when threshold is 95%
    # Prevents SL attachment on incomplete executions
```

### 3. Stop-Loss Attachment
```python
# Generate SL order after swarm completes
if algo.should_attach_stop_loss():
    sl_order = algo.get_stop_loss_order(stop_loss_pct=Decimal("2.0"))
    # For LONG: SL below weighted avg entry (e.g., 2% below)
    # For SHORT: SL above weighted avg entry (e.g., 2% above)
```

### 4. Comprehensive Audit Trail
```python
# Structured logging with prefixes for easy filtering
SWARM_START - Beginning swarm execution
SWARM_PARTS_PREPARED - Execution plan ready (5 orders)
SWARM_ORDER_SUBMIT - Submitting child order 1/5
SWARM_DELAY - Waiting between orders (1234ms)
SWARM_COMPLETE - All orders filled
SWARM_SL_PREPARED - Stop-loss order ready
```

## Configuration

```python
config = SwarmConfig(
    # Order count randomization
    min_child_orders=2,      # Minimum orders to split into
    max_child_orders=10,     # Maximum orders to split into
    
    # Timing randomization (milliseconds)
    min_delay_ms=0,          # Minimum delay between orders
    max_delay_ms=1000,       # Maximum delay (1 second)
    
    # Exchange constraints
    min_notional_usd=Decimal("5.0"),    # Minimum order value
    min_quantity=Decimal("0.001"),       # Minimum order size
)
```

## Usage Example

```python
from swarmify import SwarmClient, AlgoOrder, OrderSide, RandomSwarmAlgo, SwarmConfig
from decimal import Decimal

async def execute_swarm():
    async with SwarmClient(exchange_id="binance", ...) as client:
        # Configure swarm
        config = SwarmConfig(
            min_child_orders=3,
            max_child_orders=8,
            min_delay_ms=500,
            max_delay_ms=3000,
        )
        
        # Create algo order
        algo_order = AlgoOrder(
            id="swarm-001",
            client_order_id="swarm-001",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            total_amount=Decimal("1.0"),
            algo_name="random_swarm",
        )
        
        # Create algo with 95% minimum fill threshold
        algo = RandomSwarmAlgo(
            algo_order=algo_order,
            config=config,
            min_fill_percent=Decimal("95.0")
        )
        
        # Execute swarm
        current_price = await client.get_ticker("BTC/USDT")
        async for child_order in algo.next_slice(current_price.last):
            await client.oms.submit_order(child_order)
            # Record fills from exchange
            # algo.record_fill(filled_qty, fill_price)
        
        # Get summary
        summary = algo.get_execution_summary()
        print(f"Filled: {summary['fill_percent']}")
        print(f"Weighted Avg: ${summary['weighted_avg_price']}")
        
        # Attach stop-loss if conditions met
        if algo.should_attach_stop_loss():
            sl_order = algo.get_stop_loss_order(Decimal("2.0"))
            await client.oms.submit_order(sl_order)
```

## Safety Features

### Quantity Split Safety
- **Minimum Enforcement**: Every child order >= `min_quantity`
- **Dust Prevention**: Remainder merged with last order if too small
- **Notional Checks**: Orders meeting `min_notional_usd` requirement
- **Precision Handling**: Decimal arithmetic prevents floating-point errors

### Fill Validation
- **Threshold Enforcement**: Warns if fill rate < `min_fill_percent`
- **SL Protection**: Stop-loss only attached if threshold met
- **Invalid Fill Detection**: Rejects non-positive quantities

### Execution Safety
- **Plan Validation**: All constraints checked before execution
- **Idempotent Planning**: Plan generated once and cached
- **Error Logging**: Comprehensive error messages with context

## Production Patterns from Battle-Tested Code

This implementation incorporates patterns from production HFT systems:

1. **Two-Phase Approach**: Separate planning (fast) from execution (I/O bound)
2. **Weighted Average Calculation**: Essential for accurate P&L and SL placement
3. **Partial Fill Handling**: Real-world markets don't always fully fill orders
4. **Stop-Loss Attachment**: Automatic risk management after position entry
5. **Structured Logging**: Audit trail compliant with regulatory requirements

## Performance Characteristics

- **Planning Speed**: <1ms for typical configurations (stdlib only)
- **Memory Usage**: O(N) where N = number of child orders (typically < 10)
- **Execution Latency**: Minimal overhead, dominated by network I/O
- **Precision**: Full Decimal precision, no floating-point errors

## Integration with SwarmClient

```python
# High-level API (recommended)
await client.execute_algo_order(algo_order, config)

# Low-level API (for custom control)
algo = RandomSwarmAlgo(algo_order, config)
async for child in algo.next_slice(price):
    await client.oms.submit_order(child)
    # Handle fills...
```

## Error Handling

```python
try:
    plan = SwarmPlanner.create_plan(total, price, config)
except ValueError as e:
    # Configuration invalid (e.g., min > max)
    # Cannot split amount given constraints
    logger.error("Planning failed", error=str(e))

try:
    sl_order = algo.get_stop_loss_order(pct)
except Exception as e:
    # Weighted avg calculation failed
    # Insufficient fills
    logger.error("SL generation failed", error=str(e))
```

## Monitoring and Observability

Key metrics to track:
- **Fill Rate**: `filled_amount / total_amount`
- **Average Fill Latency**: Time from submission to fill
- **Slippage**: `weighted_avg_price - expected_price`
- **Execution Duration**: Time from first to last order
- **Stop-Loss Distance**: `abs(sl_price - entry_price) / entry_price`

## Best Practices

1. **Configure Delays Appropriately**
   - Too fast: Obvious pattern, may trigger detection
   - Too slow: Market moves away, worse execution
   - Recommended: 500-3000ms for typical markets

2. **Set Realistic Fill Thresholds**
   - 100%: Rarely achievable in practice
   - 95%: Good balance for most markets
   - 90%: Acceptable for lower liquidity

3. **Monitor Partial Fills**
   - Always check `summary['status']`
   - Don't attach SL on partial fills
   - Consider canceling unfilled orders

4. **Use Appropriate Order Counts**
   - Too few: Minimal stealth benefit
   - Too many: Excessive fees, complexity
   - Recommended: 3-8 for typical sizes

5. **Validate Configuration**
   - Always call `config.validate()` before use
   - Check `plan.validate(config)` after planning
   - Test with paper trading first

## Comparison with Other Algos

| Feature | RandomSwarm | Iceberg | TWAP |
|---------|-------------|---------|------|
| Randomness | High (3D) | Low | None |
| Stealth | Maximum | Medium | Low |
| Predictability | Minimal | Moderate | High |
| Planning Overhead | Low | None | Low |
| Weighted Avg Price | ✅ Yes | ❌ No | ❌ No |
| Partial Fill Tracking | ✅ Yes | ❌ No | ❌ No |
| Auto Stop-Loss | ✅ Yes | ❌ No | ❌ No |

## Technical References

- **Decimal Precision**: [Python Decimal Module](https://docs.python.org/3/library/decimal.html)
- **Async Generators**: [PEP 525](https://www.python.org/dev/peps/pep-0525/)
- **Structured Logging**: [Structlog Documentation](https://www.structlog.org/)
