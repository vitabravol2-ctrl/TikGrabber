# BTCUSDT Game Theory Engine v1.0.3

- Fixed false `MISSING_BOOK` by introducing cached book/depth ages in WS pipeline.
- Added explicit data-quality reasons: `WARMUP_TRADES`, `MISSING_BOOK_TICKER`, `MISSING_DEPTH`, `STALE_BOOK`, `STALE_DEPTH`, `WS_UNSTABLE`, `GOOD`, `LEGACY_REPLAY`.
- Risk gate now blocks by specific stale/missing reasons only.
- Dashboard includes compact `BOOK / DATA STATUS` diagnostics panel.
- Replay compatibility preserved for legacy events without age fields.
- Paper-only mode remains enforced.
