from decimal import Decimal

import pytest

from swarmify.algos.iceberg import IcebergAlgo
from swarmify.core.models import AlgoOrder
from swarmify.core.types import OrderSide


def _parent(amount: str) -> AlgoOrder:
    return AlgoOrder(
        id="ice-1",
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        total_amount=Decimal(amount),
    )


async def _slices(algo: IcebergAlgo) -> list[Decimal]:
    return [child.amount async for child in algo.next_slice(Decimal("100"))]


@pytest.mark.asyncio
async def test_uneven_split_puts_remainder_last():
    algo = IcebergAlgo(_parent("1.0"), slice_size=Decimal("0.3"))
    sizes = await _slices(algo)
    assert sizes == [Decimal("0.3"), Decimal("0.3"), Decimal("0.3"), Decimal("0.1")]


@pytest.mark.asyncio
async def test_even_split():
    algo = IcebergAlgo(_parent("1.0"), slice_size=Decimal("0.5"))
    sizes = await _slices(algo)
    assert sizes == [Decimal("0.5"), Decimal("0.5")]


@pytest.mark.asyncio
async def test_slices_sum_to_parent():
    algo = IcebergAlgo(_parent("2.345"), slice_size=Decimal("0.7"))
    sizes = await _slices(algo)
    assert sum(sizes) == Decimal("2.345")


def test_non_positive_slice_size_rejected():
    with pytest.raises(ValueError):
        IcebergAlgo(_parent("1.0"), slice_size=Decimal("0"))


@pytest.mark.asyncio
async def test_slice_larger_than_parent_yields_one_child():
    algo = IcebergAlgo(_parent("0.4"), slice_size=Decimal("1.0"))
    sizes = await _slices(algo)
    assert sizes == [Decimal("0.4")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "total,slice_size",
    [
        ("10", "0.1"),
        ("3.333", "0.7"),
        ("0.001", "0.001"),
        ("99.9", "10"),
    ],
)
async def test_slices_always_sum_to_parent(total, slice_size):
    algo = IcebergAlgo(_parent(total), slice_size=Decimal(slice_size))
    sizes = await _slices(algo)
    assert sum(sizes) == Decimal(total)
    assert all(s > 0 for s in sizes)
