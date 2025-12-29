"""Swarmify Execution Engine - High-performance async algorithmic trading library."""

from .client import SwarmClient
from .core.models import Order, AlgoOrder, Trade, Ticker, Balance
from .core.types import OrderSide, OrderType, OrderStatus, TimeInForce
from .algos.random_swarm import RandomSwarmAlgo
from .algos.swarm_planner import SwarmConfig

__version__ = "0.1.0"

__all__ = [
    "SwarmClient",
    "Order",
    "AlgoOrder",
    "Trade",
    "Ticker",
    "Balance",
    "OrderSide",
    "OrderType",
    "OrderStatus",
    "TimeInForce",
    "RandomSwarmAlgo",
    "SwarmConfig",
]
