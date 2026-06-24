"""Base interface for execution algorithms."""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from decimal import Decimal

from ..core.models import AlgoOrder, Order


class ExecutionAlgo(ABC):
    """Turns a parent :class:`AlgoOrder` into a stream of child orders.

    An algorithm owns the slicing logic only; it does not place orders. The
    caller (typically the OMS) consumes :meth:`next_slice` and submits each
    child, then feeds fills back via :meth:`record_fill` so the algorithm can
    track progress.
    """

    name: str = "base"

    def __init__(self, algo_order: AlgoOrder) -> None:
        self.parent_order = algo_order

    @abstractmethod
    def next_slice(self, current_market_price: Decimal) -> AsyncGenerator[Order]:
        """Yield child orders in execution order.

        Implementations are async generators; delays between child orders are
        the algorithm's responsibility and happen inside this coroutine.
        """
        raise NotImplementedError

    def record_fill(self, filled_qty: Decimal, fill_price: Decimal) -> None:
        """Record a fill so progress and average price stay current.

        The default implementation only updates the parent's filled amount.
        Algorithms that need richer accounting override this.
        """
        if filled_qty <= 0:
            return
        self.parent_order.filled_amount += filled_qty
