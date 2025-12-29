"""
Example: Random Swarm Order Execution with Production Features

This example demonstrates all features of the RandomSwarmAlgo:
- Two-phase execution (planning → execution)
- Weighted average entry price calculation
- Partial fill tracking and validation
- Stop-loss attachment after swarm completion
- Comprehensive audit trail logging
"""

import asyncio
from decimal import Decimal
from swarmify import (
    SwarmClient,
    AlgoOrder,
    OrderSide,
    OrderType,
    RandomSwarmAlgo,
    SwarmConfig,
)


async def execute_random_swarm():
    """Execute a Random Swarm order with full monitoring."""

    # Initialize client
    async with SwarmClient(
        exchange_id="binance", api_key="your_api_key", api_secret="your_api_secret"
    ) as client:

        # Configure swarm parameters
        config = SwarmConfig(
            min_child_orders=3,
            max_child_orders=8,
            min_delay_ms=500,  # 0.5 seconds minimum delay
            max_delay_ms=3000,  # 3 seconds maximum delay
            min_notional_usd=Decimal("10.0"),
            min_quantity=Decimal("0.001"),
        )

        # Create algo order for swarm execution
        algo_order = AlgoOrder(
            id="swarm-btc-buy-001",
            client_order_id="swarm-btc-buy-001",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            total_amount=Decimal("0.5"),  # 0.5 BTC total
            algo_name="random_swarm",
        )

        # Create RandomSwarmAlgo with 95% minimum fill threshold
        algo = RandomSwarmAlgo(
            algo_order=algo_order,
            config=config,
            min_fill_percent=Decimal("95.0"),  # Warn if < 95% filled
        )

        print("=" * 80)
        print("SWARM EXECUTION STARTING")
        print("=" * 80)
        print(f"Symbol: {algo_order.symbol}")
        print(f"Side: {algo_order.side.value}")
        print(f"Total Amount: {algo_order.total_amount} BTC")
        print(
            f"Min Orders: {config.min_child_orders}, Max Orders: {config.max_child_orders}"
        )
        print(f"Delay Range: {config.min_delay_ms}-{config.max_delay_ms}ms")
        print(f"Min Fill Threshold: {algo.min_fill_percent}%")
        print("=" * 80)
        print()

        # Execute the algo order
        # In production, this would be: await client.execute_algo_order(algo_order, config)
        # For this example, we'll simulate the execution flow

        # Phase 1: Planning happens automatically on first next_slice() call
        # Phase 2: Execution with simulated fills

        current_market_price = Decimal("45000.0")

        # Simulate order execution and fill tracking
        async for child_order in algo.next_slice(current_market_price):
            print(f"📤 SUBMITTED: {child_order.client_order_id}")
            print(f"   Amount: {child_order.amount} BTC @ ${child_order.price}")

            # Simulate order fill (in production, this would come from exchange)
            # For demonstration, assume full fill with slight slippage
            fill_price = child_order.price * Decimal("1.0001")  # 0.01% slippage

            # Record the fill
            algo.record_fill(filled_qty=child_order.amount, fill_price=fill_price)

            print(f"   ✅ FILLED: {child_order.amount} BTC @ ${fill_price}")
            print(f"   Weighted Avg Entry: ${algo.get_weighted_avg_price()}")
            print()

        # Get execution summary
        print("=" * 80)
        print("SWARM EXECUTION SUMMARY")
        print("=" * 80)
        summary = algo.get_execution_summary()

        for key, value in summary.items():
            if key == "warning":
                print(f"⚠️  {key.upper()}: {value}")
            else:
                print(f"{key}: {value}")

        print("=" * 80)
        print()

        # Check if we should attach stop-loss
        if algo.should_attach_stop_loss():
            print("=" * 80)
            print("STOP-LOSS ATTACHMENT")
            print("=" * 80)

            # Generate stop-loss order (2% below entry for long, 2% above for short)
            stop_loss_pct = Decimal("2.0")
            sl_order = algo.get_stop_loss_order(stop_loss_pct)

            if sl_order:
                print(f"✅ Stop-Loss Order Prepared:")
                print(f"   Order ID: {sl_order.id}")
                print(f"   Symbol: {sl_order.symbol}")
                print(f"   Side: {sl_order.side.value}")
                print(f"   Type: {sl_order.order_type.value}")
                print(f"   Trigger Price: ${sl_order.price}")
                print(f"   Amount: {sl_order.amount} BTC")
                print(f"   Entry Price: ${algo.get_weighted_avg_price()}")
                print(f"   Stop-Loss %: {stop_loss_pct}%")

                # In production, submit the SL order:
                # await client.oms.submit_order(sl_order)
                print(f"\n   📤 Ready to submit (in production mode)")
            else:
                print("❌ Stop-Loss order could not be generated")

            print("=" * 80)
        else:
            print("⚠️  Stop-Loss attachment skipped - insufficient fill percentage")


async def execute_swarm_with_partial_fill():
    """Demonstrate partial fill detection and warnings."""

    print("\n\n")
    print("=" * 80)
    print("EXAMPLE 2: PARTIAL FILL SCENARIO")
    print("=" * 80)
    print()

    config = SwarmConfig(
        min_child_orders=5,
        max_child_orders=5,  # Force exactly 5 orders
    )

    algo_order = AlgoOrder(
        id="swarm-eth-buy-002",
        client_order_id="swarm-eth-buy-002",
        symbol="ETH/USDT",
        side=OrderSide.BUY,
        total_amount=Decimal("10.0"),
    )

    algo = RandomSwarmAlgo(
        algo_order=algo_order, config=config, min_fill_percent=Decimal("95.0")
    )

    current_market_price = Decimal("3000.0")

    # Simulate execution with only 3 out of 5 orders filled (60% fill rate)
    order_count = 0
    async for child_order in algo.next_slice(current_market_price):
        order_count += 1

        # Only fill first 3 orders
        if order_count <= 3:
            fill_price = child_order.price
            algo.record_fill(child_order.amount, fill_price)
            print(f"✅ Order {order_count} FILLED: {child_order.amount} ETH")
        else:
            print(f"❌ Order {order_count} NOT FILLED: {child_order.amount} ETH")

    print()
    summary = algo.get_execution_summary()

    print("EXECUTION SUMMARY:")
    print(f"Status: {summary['status']}")
    print(f"Fill Percent: {summary['fill_percent']}")
    print(f"Meets Threshold: {summary['meets_threshold']}")

    if "warning" in summary:
        print(f"\n⚠️  WARNING: {summary['warning']}")

    # Check SL attachment
    if algo.should_attach_stop_loss():
        print("\n✅ Stop-Loss can be attached")
    else:
        print("\n❌ Stop-Loss NOT attached - insufficient fills")

    print("=" * 80)


if __name__ == "__main__":
    # Run both examples
    asyncio.run(execute_random_swarm())
    asyncio.run(execute_swarm_with_partial_fill())
