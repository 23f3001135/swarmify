"""Async SQLite persistence for order state and the parent/child audit trail."""

from decimal import Decimal

import aiosqlite

from ..core.models import Order
from ..core.types import OrderSide, OrderStatus, OrderType, TimeInForce

_SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id                   TEXT PRIMARY KEY,
    client_order_id      TEXT NOT NULL UNIQUE,
    parent_id            TEXT,
    exchange_order_id    TEXT,
    symbol               TEXT NOT NULL,
    side                 TEXT NOT NULL,
    order_type           TEXT NOT NULL,
    price                TEXT,
    amount               TEXT NOT NULL,
    filled               TEXT NOT NULL,
    remaining            TEXT,
    average_price        TEXT,
    status               TEXT NOT NULL,
    time_in_force        TEXT NOT NULL,
    timestamp            INTEGER NOT NULL,
    last_update_timestamp INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_orders_parent ON orders(parent_id);
"""

_COLUMNS = [
    "id",
    "client_order_id",
    "parent_id",
    "exchange_order_id",
    "symbol",
    "side",
    "order_type",
    "price",
    "amount",
    "filled",
    "remaining",
    "average_price",
    "status",
    "time_in_force",
    "timestamp",
    "last_update_timestamp",
]


class OrderStore:
    """Single long-lived connection in WAL mode for concurrent reads."""

    def __init__(self, path: str = ":memory:") -> None:
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        if self.path != ":memory:":
            await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def upsert(self, order: Order) -> None:
        conn = self._require_conn()
        placeholders = ", ".join("?" for _ in _COLUMNS)
        updates = ", ".join(f"{c}=excluded.{c}" for c in _COLUMNS if c != "id")
        await conn.execute(
            f"INSERT INTO orders ({', '.join(_COLUMNS)}) VALUES ({placeholders}) "
            f"ON CONFLICT(id) DO UPDATE SET {updates}",
            self._to_row(order),
        )
        await conn.commit()

    async def get(self, order_id: str) -> Order | None:
        conn = self._require_conn()
        async with conn.execute(
            "SELECT * FROM orders WHERE id = ?", (order_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return self._from_row(row) if row else None

    async def children_of(self, parent_id: str) -> list[Order]:
        conn = self._require_conn()
        async with conn.execute(
            "SELECT * FROM orders WHERE parent_id = ? ORDER BY timestamp", (parent_id,)
        ) as cursor:
            rows = await cursor.fetchall()
        return [self._from_row(row) for row in rows]

    def _require_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("OrderStore is not connected; call connect() first")
        return self._conn

    @staticmethod
    def _to_row(order: Order) -> tuple[object, ...]:
        def s(value: Decimal | None) -> str | None:
            return str(value) if value is not None else None

        return (
            order.id,
            order.client_order_id,
            order.parent_id,
            order.exchange_order_id,
            order.symbol,
            order.side.value,
            order.order_type.value,
            s(order.price),
            s(order.amount),
            s(order.filled),
            s(order.remaining),
            s(order.average_price),
            order.status.value,
            order.time_in_force.value,
            order.timestamp,
            order.last_update_timestamp,
        )

    @staticmethod
    def _from_row(row: aiosqlite.Row) -> Order:
        def d(value: str | None) -> Decimal | None:
            return Decimal(value) if value is not None else None

        return Order(
            id=row["id"],
            client_order_id=row["client_order_id"],
            parent_id=row["parent_id"],
            exchange_order_id=row["exchange_order_id"],
            symbol=row["symbol"],
            side=OrderSide(row["side"]),
            order_type=OrderType(row["order_type"]),
            price=d(row["price"]),
            amount=d(row["amount"]) or Decimal("0"),
            filled=d(row["filled"]) or Decimal("0"),
            remaining=d(row["remaining"]),
            average_price=d(row["average_price"]),
            status=OrderStatus(row["status"]),
            time_in_force=TimeInForce(row["time_in_force"]),
            timestamp=row["timestamp"],
            last_update_timestamp=row["last_update_timestamp"],
        )
