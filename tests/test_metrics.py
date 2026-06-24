from swarmify.utils.metrics import Metrics


def test_counters_accumulate():
    m = Metrics()
    m.incr("orders.submitted")
    m.incr("orders.submitted", 2)
    assert m.counters["orders.submitted"] == 3


def test_latency_tracks_count_avg_and_max():
    m = Metrics()
    for value in (10.0, 20.0, 30.0):
        m.observe_latency("submit", value)

    snap = m.snapshot()["latency_ms"]["submit"]
    assert snap["count"] == 3
    assert snap["avg"] == 20.0
    assert snap["max"] == 30.0


def test_snapshot_shape():
    m = Metrics()
    m.incr("a")
    m.observe_latency("b", 5.0)
    snap = m.snapshot()
    assert snap["counters"] == {"a": 1}
    assert set(snap["latency_ms"]["b"]) == {"count", "avg", "max"}


def test_unobserved_latency_is_absent():
    assert Metrics().snapshot()["latency_ms"] == {}
