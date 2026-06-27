# Error Log — AV Scenario Engine

Format: one entry per error encountered during development.

---

## Template

### ERR-XXX: [Short description]
**Date:** YYYY-MM-DD
**Stage:** ingest / detect / featurize / curate / serve / pipeline / analytics
**Error message:**
```
paste exact error here
```
**Root cause:** What actually went wrong and why.
**Fix:** What you changed to resolve it.
**Lesson:** What to watch for next time (optional but valuable).

---

## Log

### ERR-001: Pandera type mismatch on n_agents column
**Date:** 2026-06-27
**Stage:** featurize
**Error message:**
```
pandera.errors.SchemaError: expected column 'n_agents' to have type Int64, got UInt32
```
**Root cause:** Polars' `n_unique()` returns UInt32 by default. The Pandera FeatureSchema declares `n_agents: int` which maps to Int64.
**Fix:** Added explicit cast `pl.col("n_agents").cast(pl.Int64)` in `featurize.py` before validation.
**Lesson:** Polars unsigned integer returns from aggregation functions don't match Pandera's default signed int expectations. Always check aggregation return types against contracts.
