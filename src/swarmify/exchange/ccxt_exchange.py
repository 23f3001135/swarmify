"""CCXT-backed exchange adapter with timeouts on every network call."""

import asyncio
from decimal import Decimal
from typing import Any

import ccxt.async_support as ccxt_async
import structlog

from ..core.models import Balance, Order, Ticker
from ..core.types import OrderStatus, OrderType
from .base import BaseExchange

logger = structlog.get_logger(__name__)

# CCXT reports order state with these strings; map them onto our enum.
_STATUS_MAP = {
    "open": OrderStatus.OPEN,
    "closed": OrderStatus.FILLED,
    "canceled": OrderStatus.CANCELED,
    "cancelled": OrderStatus.CANCELED,
    "rejected": OrderStatus.REJECTED,
    "expired": OrderStatus.EXPIRED,
}

_TYPE_MAP = {
    OrderType.MARKET: "market",
    OrderType.LIMIT: "limit",
    OrderType.STOP_MARKET: "stop_market",
    OrderType.STOP_LIMIT: "stop_limit",
}


def _dec(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


class CcxtExchange(BaseExchange):
    """Adapter over ``ccxt.async_support`` for a single venue."""

    def __init__(
        self,
        exchange_id: str,
        api_key: str = "",
        secret: str = "",
        *,
        sandbox: bool = True,
        timeout: float = 15.0,
        options: dict[str, Any] | None = None,
    ) -> None:
        self.name = exchange_id
        self.timeout = timeout
        try:
            factory = getattr(ccxt_async, exchange_id)
        except AttributeError as exc:
            raise ValueError(f"unknown ccxt exchange: {exchange_id}") from exc

        self._client = factory(
            {
                "apiKey": api_key,
                "secret": secret,
                "enableRateLimit": True,
                "options": options or {},
            }
        )
        if sandbox:
            self._client.set_sandbox_mode(True)

    async def _call(self, coro: Any) -> Any:
        return await asyncio.wait_for(coro, timeout=self.timeout)

    async def create_order(self, order: Order) -> Order:
        params: dict[str, Any] = {"clientOrderId": order.client_order_id}
        if order.order_type in (OrderType.STOP_MARKET, OrderType.STOP_LIMIT):
            params["stopPrice"] = (
                float(order.price) if order.price is not None else None
            )

        result = await self._call(
            self._client.create_order(
                symbol=order.symbol,
                type=_TYPE_MAP[order.order_type],
                side=order.side.value,
                amount=float(order.amount),
                price=float(order.price) if order.price is not None else None,
                params=params,
            )
        )
        return self._apply_result(order, result)

    async def cancel_order(self, symbol: str, exchange_order_id: str) -> None:
        await self._call(self._client.cancel_order(exchange_order_id, symbol))

    async def fetch_order(self, symbol: str, exchange_order_id: str) -> Order:
        result = await self._call(self._client.fetch_order(exchange_order_id, symbol))
        return self._order_from_ccxt(result)

    async def fetch_ticker(self, symbol: str) -> Ticker:
        result = await self._call(self._client.fetch_ticker(symbol))
        return Ticker(
            symbol=symbol,
            last=_dec(result.get("last")) or Decimal("0"),
            bid=_dec(result.get("bid")),
            ask=_dec(result.get("ask")),
            timestamp=int(result.get("timestamp") or 0),
        )

    async def fetch_balances(self) -> dict[str, Balance]:
        result = await self._call(self._client.fetch_balance())
        totals = result.get("total", {})
        free = result.get("free", {})
        used = result.get("used", {})
        return {
            currency: Balance(
                currency=currency,
                free=_dec(free.get(currency)) or Decimal("0"),
                used=_dec(used.get(currency)) or Decimal("0"),
                total=_dec(amount) or Decimal("0"),
            )
            for currency, amount in totals.items()
            if amount
        }

    async def close(self) -> None:
        await self._client.close()

    def _apply_result(self, order: Order, result: dict[str, Any]) -> Order:
        order.exchange_order_id = result.get("id")
        order.status = _STATUS_MAP.get(result.get("status", ""), order.status)
        filled = _dec(result.get("filled"))
        if filled is not None:
            order.filled = filled
            order.remaining = order.amount - filled
        order.average_price = _dec(result.get("average")) or order.average_price
        return order

    def _order_from_ccxt(self, result: dict[str, Any]) -> Order:
        amount = _dec(result.get("amount")) or Decimal("0")
        filled = _dec(result.get("filled")) or Decimal("0")
        return Order(
            id=result.get("clientOrderId") or result["id"],
            client_order_id=result.get("clientOrderId") or result["id"],
            exchange_order_id=result.get("id"),
            symbol=result["symbol"],
            side=result["side"],
            order_type=result.get("type", "limit"),
            amount=amount,
            price=_dec(result.get("price")),
            filled=filled,
            remaining=amount - filled,
            average_price=_dec(result.get("average")),
            status=_STATUS_MAP.get(result.get("status", ""), OrderStatus.OPEN),
        )
