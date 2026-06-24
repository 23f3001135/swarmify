# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project uses semantic
versioning.

## [0.3.0]

### Added
- `RandomSwarmAlgo`: randomised order-count, size and timing, built from a
  pre-computed `SwarmPlan` so plans can be inspected before any order is sent.
- Fill tracking on the swarm: weighted-average entry, partial-fill detection
  against `min_fill_percent`, and a derived stop-market via
  `get_stop_loss_order`.
- `IcebergAlgo`: fixed-size slicing with the remainder in the trailing slice.
- `SwarmClient` with `for_exchange` constructor, async context management and
  `execute_algo_order` / `execute_algo` helpers.
- `OMS` with idempotent submission, latency metrics and an aiosqlite store that
  records the parent/child audit trail.
- `RiskManager` pre-trade checks: notional and quantity limits, and refusal of
  market orders that cannot be priced.
- `CcxtExchange` adapter with a timeout on every network call.

### Changed
- `core.types` enums now use `enum.StrEnum`.
- Order and parent-order models reject unknown fields.

[0.3.0]: https://example.com/swarmify/releases/0.3.0
