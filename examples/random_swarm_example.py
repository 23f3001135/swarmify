"""Work a parent order with the random swarm algorithm.

Runs offline: instead of hitting a venue it feeds each child straight back as a
fill so you can watch the plan, the weighted-average entry and the derived stop
without credentials. The live wiring is shown in the comment at the bottom.
"""

import asyncio
from decimal import Decimal

from swarmify import AlgoOrder, OrderSide, RandomSwarmAlgo, SwarmConfig


async def main() -> None:
    config = SwarmConfig(
        min_child_orders=3,
        max_child_orders=8,
        min_delay_ms=0,
        max_delay_ms=50,
    )
    parent = AlgoOrder(
        id="swarm-btc-001",
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        total_amount=Decimal("0.5"),
    )
    algo = RandomSwarmAlgo(parent, config=config, min_fill_percent=Decimal("95.0"))

    reference_price = Decimal("45000")
    async for child in algo.next_slice(reference_price):
        # Stand in for the exchange: assume each child fills at its limit.
        algo.record_fill(child.amount, child.price)
        print(f"filled {child.amount} @ {child.price} -> {child.client_order_id}")

    summary = algo.get_execution_summary()
    print(f"\nstatus={summary['status']} fill={summary['fill_percent']}")
    print(f"weighted avg entry={summary['weighted_avg_price']}")

    if algo.should_attach_stop_loss():
        stop = algo.get_stop_loss_order(Decimal("2.0"))
        assert stop is not None
        print(f"stop {stop.side} {stop.amount} @ {stop.price}")


# Live usage submits each child through the OMS instead of simulating fills:
#
#     async with SwarmClient.for_exchange(
#         "binance", api_key, secret, sandbox=True
#     ) as client:
#         algo = await client.execute_algo_order(
#             "BTC/USDT", OrderSide.BUY, Decimal("0.5"), "random_swarm",
#             algo_params={"min_child_orders": 3, "max_child_orders": 8},
#         )
#         if algo.should_attach_stop_loss():
#             await client.submit_order(algo.get_stop_loss_order(Decimal("2.0")))


if __name__ == "__main__":
    asyncio.run(main())
