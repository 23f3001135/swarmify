"""High-level entry point: wire an exchange, OMS, risk and storage together."""

import uuid
from decimal import Decimal
from typing import Any

import structlog

from .algos.base import ExecutionAlgo
from .algos.iceberg import IcebergAlgo
from .algos.random_swarm import RandomSwarmAlgo
from .algos.swarm_planner import SwarmConfig
from .core.models import AlgoOrder, Order, Ticker
from .core.types import OrderSide
from .exchange.base import BaseExchange
from .exchange.ccxt_exchange import CcxtExchange
from .execution.oms import OMS
from .execution.risk import RiskManager
from .persistence.store import OrderStore
from .utils.metrics import Metrics

logger = structlog.get_logger(__name__)


class SwarmClient:
    """Owns the engine's moving parts and exposes a small async surface.

    Construct directly with an injected :class:`BaseExchange` (handy for tests),
    or via :meth:`for_exchange` to build a CCXT-backed venue from credentials.
    Use as an async context manager so storage and sockets are opened and
    closed cleanly.
    """

    def __init__(
        self,
        exchange: BaseExchange,
        *,
        risk: RiskManager | None = None,
        store: OrderStore | None = None,
        metrics: Metrics | None = None,
    ) -> None:
        self.exchange = exchange
        self.store = store
        self.metrics = metrics or Metrics()
        self.oms = OMS(exchange, risk=risk, store=store, metrics=self.metrics)

    @classmethod
    def for_exchange(
        cls,
        exchange_id: str,
        api_key: str = "",
        secret: str = "",
        *,
        sandbox: bool = True,
        timeout: float = 15.0,
        risk: RiskManager | None = None,
        db_path: str | None = None,
    ) -> "SwarmClient":
        exchange = CcxtExchange(
            exchange_id, api_key, secret, sandbox=sandbox, timeout=timeout
        )
        store = OrderStore(db_path) if db_path else None
        return cls(exchange, risk=risk, store=store)

    async def __aenter__(self) -> "SwarmClient":
        if self.store is not None:
            await self.store.connect()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self.exchange.close()
        if self.store is not None:
            await self.store.close()

    async def get_ticker(self, symbol: str) -> Ticker:
        return await self.exchange.fetch_ticker(symbol)

    async def submit_order(
        self, order: Order, reference_price: Decimal | None = None
    ) -> Order:
        return await self.oms.submit_order(order, reference_price)

    async def execute_algo(
        self, algo: ExecutionAlgo, reference_price: Decimal | None = None
    ) -> ExecutionAlgo:
        """Run an algorithm to completion, submitting each child via the OMS."""
        price = reference_price
        if price is None:
            price = (await self.get_ticker(algo.parent_order.symbol)).last

        async for child in algo.next_slice(price):
            await self.oms.submit_order(child, reference_price=price)
        return algo

    async def execute_algo_order(
        self,
        symbol: str,
        side: OrderSide | str,
        amount: Decimal,
        algo: str = "random_swarm",
        algo_params: dict[str, Any] | None = None,
        reference_price: Decimal | None = None,
    ) -> ExecutionAlgo:
        """Build a parent order, pick the algorithm, and work it.

        Returns the constructed algorithm so the caller can inspect fills,
        request an execution summary, or attach a stop afterwards.
        """
        parent = AlgoOrder(
            id=str(uuid.uuid4()),
            symbol=symbol,
            side=OrderSide(side) if isinstance(side, str) else side,
            total_amount=amount,
            algo_name=algo,
            params=algo_params or {},
        )
        instance = self._build_algo(parent, algo, algo_params or {})
        return await self.execute_algo(instance, reference_price)

    @staticmethod
    def _build_algo(
        parent: AlgoOrder, algo: str, params: dict[str, Any]
    ) -> ExecutionAlgo:
        if algo == "random_swarm":
            config = SwarmConfig(**params) if params else None
            return RandomSwarmAlgo(parent, config=config)
        if algo == "iceberg":
            slice_size = params.get("slice_size")
            if slice_size is None:
                raise ValueError("iceberg requires a 'slice_size' parameter")
            return IcebergAlgo(parent, slice_size=Decimal(str(slice_size)))
        raise ValueError(f"unknown algo: {algo}")
