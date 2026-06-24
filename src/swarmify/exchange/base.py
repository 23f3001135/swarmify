"""Exchange interface the rest of the engine codes against."""

from abc import ABC, abstractmethod

from ..core.models import Balance, Order, Ticker


class BaseExchange(ABC):
    """Minimal async surface every venue adapter must provide.

    Implementations own connection handling and timeouts; everything above the
    adapter speaks in :mod:`swarmify.core.models` types only.
    """

    name: str

    @abstractmethod
    async def create_order(self, order: Order) -> Order:
        """Place ``order`` and return it updated with the venue's id and state."""

    @abstractmethod
    async def cancel_order(self, symbol: str, exchange_order_id: str) -> None:
        """Cancel a resting order by its venue id."""

    @abstractmethod
    async def fetch_order(self, symbol: str, exchange_order_id: str) -> Order:
        """Fetch the current state of a previously placed order."""

    @abstractmethod
    async def fetch_ticker(self, symbol: str) -> Ticker:
        """Return the latest top-of-book snapshot for ``symbol``."""

    @abstractmethod
    async def fetch_balances(self) -> dict[str, Balance]:
        """Return free/used/total balances keyed by currency."""

    @abstractmethod
    async def close(self) -> None:
        """Release any network resources held by the adapter."""
