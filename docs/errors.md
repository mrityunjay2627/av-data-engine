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

---

### ERR-002: ValueError in generate.py when n_timesteps < 40
**Date:** 2026-06-27
**Stage:** generate
**Error message:**
```
ValueError: low >= high
```
**Root cause:** `rng.integers(10, n_timesteps - 25)` produces a negative upper bound when n_timesteps < 35. The cut-in injection assumed ≥91 timesteps (the default) but tests passed n_timesteps=20.
**Fix:** Added guard `if rng.random() < 0.10 and n_timesteps > 40` before injection. Same fix for hard-brake injection.
**Lesson:** Parameterized generators must guard all random-range calls against caller-provided bounds. Test with small inputs, not just defaults.

---

### ERR-003: pl.concat fails with ShapeError on column order mismatch
**Date:** 2026-06-27
**Stage:** detect
**Error message:**
```
polars.exceptions.ShapeError: unable to vstack, column names don't match: "event_type" and "timestep_start"
```
**Root cause:** Empty DataFrames (from `pl.DataFrame(schema={...})`) had columns in dict-insertion order, while non-empty DataFrames from `group_by().agg().with_columns()` had columns in a different order (with_columns appends). Polars concat requires identical column order.
**Fix:** Added explicit `.select(EVENT_COLS)` before concat to enforce consistent column order across all three event types.
**Lesson:** Never trust implicit column ordering across different Polars operations. Always `.select()` into a canonical order before concat.
