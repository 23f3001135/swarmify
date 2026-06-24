"""Lightweight in-process counters and latency histograms.

The engine runs inside a single event loop, so a plain dict is enough; callers
that need durable metrics scrape :meth:`Metrics.snapshot` and forward it to
their own stack (Prometheus, statsd, etc.).
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _Latency:
    count: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0

    def add(self, value_ms: float) -> None:
        self.count += 1
        self.total_ms += value_ms
        if value_ms > self.max_ms:
            self.max_ms = value_ms

    @property
    def avg_ms(self) -> float:
        return self.total_ms / self.count if self.count else 0.0


@dataclass
class Metrics:
    counters: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    latencies: dict[str, _Latency] = field(
        default_factory=lambda: defaultdict(_Latency)
    )

    def incr(self, name: str, amount: int = 1) -> None:
        self.counters[name] += amount

    def observe_latency(self, name: str, value_ms: float) -> None:
        self.latencies[name].add(value_ms)

    def snapshot(self) -> dict[str, Any]:
        return {
            "counters": dict(self.counters),
            "latency_ms": {
                name: {
                    "count": lat.count,
                    "avg": round(lat.avg_ms, 3),
                    "max": round(lat.max_ms, 3),
                }
                for name, lat in self.latencies.items()
            },
        }
