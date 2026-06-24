from decimal import Decimal

import pytest

from swarmify.core.models import Balance, Order, Ticker
from swarmify.core.types import OrderStatus
from swarmify.exchange.base import BaseExchange


class FakeExchange(BaseExchange):
    """In-memory exchange for testing the OMS and client without a network.

    Orders fill immediately at their limit price unless ``fill`` is False, in
    which case they rest open. Set ``fail_next`` to simulate a transport error
    on the next ``create_order``.
    """

    def __init__(self, fill: bool = True) -> None:
        self.name = "fake"
        self.fill = fill
        self.fail_next = False
        self.created: list[Order] = []
        self.canceled: list[tuple[str, str]] = []
        self._seq = 0

    async def create_order(self, order: Order) -> Order:
        self.created.append(order)
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("simulated transport error")
        self._seq += 1
        order.exchange_order_id = f"ex-{self._seq}"
        if self.fill:
            order.status = OrderStatus.FILLED
            order.filled = order.amount
            order.remaining = Decimal("0")
            order.average_price = order.price
        else:
            order.status = OrderStatus.OPEN
        return order

    async def cancel_order(self, symbol: str, exchange_order_id: str) -> None:
        self.canceled.append((symbol, exchange_order_id))

    async def fetch_order(self, symbol: str, exchange_order_id: str) -> Order:
        raise NotImplementedError

    async def fetch_ticker(self, symbol: str) -> Ticker:
        return Ticker(
            symbol=symbol,
            last=Decimal("100"),
            bid=Decimal("99"),
            ask=Decimal("101"),
        )

    async def fetch_balances(self) -> dict[str, Balance]:
        return {}

    async def close(self) -> None:
        pass


@pytest.fixture
def fake_exchange() -> FakeExchange:
    return FakeExchange()
