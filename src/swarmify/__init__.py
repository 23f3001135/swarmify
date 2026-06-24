"""Swarmify: an async algorithmic execution engine for crypto venues."""

from .algos.base import ExecutionAlgo
from .algos.iceberg import IcebergAlgo
from .algos.random_swarm import RandomSwarmAlgo
from .algos.swarm_planner import SwarmConfig, SwarmPlan, SwarmPlanner
from .client import SwarmClient
from .core.models import AlgoOrder, Balance, Order, Ticker, Trade
from .core.types import OrderSide, OrderStatus, OrderType, TimeInForce
from .exchange.base import BaseExchange
from .exchange.ccxt_exchange import CcxtExchange
from .execution.oms import OMS
from .execution.risk import RiskDecision, RiskLimits, RiskManager
from .persistence.store import OrderStore
from .utils.metrics import Metrics

__version__ = "0.3.0"

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
    "ExecutionAlgo",
    "RandomSwarmAlgo",
    "IcebergAlgo",
    "SwarmConfig",
    "SwarmPlan",
    "SwarmPlanner",
    "BaseExchange",
    "CcxtExchange",
    "OMS",
    "RiskManager",
    "RiskLimits",
    "RiskDecision",
    "OrderStore",
    "Metrics",
]
