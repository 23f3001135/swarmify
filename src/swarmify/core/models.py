"""Domain models shared across the engine.

All monetary and size fields use :class:`decimal.Decimal`. Exchanges and the OMS
never hand floats to one another, so rounding is explicit and reproducible.
"""

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..utils.timeutil import now_ms
from .types import OrderSide, OrderStatus, OrderType, TimeInForce


class Order(BaseModel):
    """A single order destined for (or already on) an exchange."""

    model_config = ConfigDict(extra="forbid")

    id: str
    client_order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    amount: Decimal

    price: Decimal | None = None
    parent_id: str | None = None
    exchange_order_id: str | None = None

    filled: Decimal = Decimal("0")
    remaining: Decimal | None = None
    average_price: Decimal | None = None
    fee: Decimal | None = None

    status: OrderStatus = OrderStatus.PENDING
    time_in_force: TimeInForce = TimeInForce.GTC

    timestamp: int = Field(default_factory=now_ms)
    last_update_timestamp: int = Field(default_factory=now_ms)

    @field_validator("amount")
    @classmethod
    def _amount_positive(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("amount must be > 0")
        return value

    @field_validator("price")
    @classmethod
    def _price_positive(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and value <= 0:
            raise ValueError("price must be > 0")
        return value

    @model_validator(mode="after")
    def _default_remaining(self) -> "Order":
        if self.remaining is None:
            self.remaining = self.amount - self.filled
        return self

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            OrderStatus.FILLED,
            OrderStatus.CANCELED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        )


class AlgoOrder(BaseModel):
    """A parent order to be worked by an execution algorithm."""

    model_config = ConfigDict(extra="forbid")

    id: str
    symbol: str
    side: OrderSide
    total_amount: Decimal

    algo_name: str = "random_swarm"
    params: dict[str, Any] = Field(default_factory=dict)
    filled_amount: Decimal = Decimal("0")
    status: OrderStatus = OrderStatus.PENDING

    timestamp: int = Field(default_factory=now_ms)
    last_update_timestamp: int = Field(default_factory=now_ms)

    @field_validator("total_amount")
    @classmethod
    def _total_positive(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("total_amount must be > 0")
        return value

    @property
    def remaining_amount(self) -> Decimal:
        return self.total_amount - self.filled_amount


class Trade(BaseModel):
    """A fill against an order."""

    id: str
    order_id: str
    symbol: str
    side: OrderSide
    price: Decimal
    amount: Decimal
    fee: Decimal = Decimal("0")
    fee_currency: str | None = None
    is_maker: bool = False
    timestamp: int = Field(default_factory=now_ms)


class Ticker(BaseModel):
    """Top-of-book snapshot for a symbol."""

    symbol: str
    last: Decimal
    bid: Decimal | None = None
    ask: Decimal | None = None
    timestamp: int = Field(default_factory=now_ms)


class Balance(BaseModel):
    """Per-currency account balance."""

    currency: str
    free: Decimal = Decimal("0")
    used: Decimal = Decimal("0")
    total: Decimal = Decimal("0")
