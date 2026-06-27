# AV Scenario Engine

A scenario-mining and curation pipeline for autonomous vehicle driving logs.

Ingests Waymo Open Motion Dataset trajectories (or synthetic equivalents), detects safety-relevant driving events (hard brakes, cut-ins, near-misses), deduplicates and curates a balanced training subset, and serves it as a queryable catalog — the "data engine" loop that feeds AV perception and planning models.

## Architecture

**Single-node lakehouse** — designed for scale, demonstrated on a sample.

| Layer | Tool | Why |
|-------|------|-----|
| Storage | Hive-partitioned Parquet (Iceberg-ready) | Columnar, partition pruning, DuckDB-native |
| Transform | Polars | Streaming-capable DataFrame engine, no Spark overhead |
| Query | DuckDB | In-process OLAP, native Hive partition reads |
| Orchestration | Dagster | Software-defined assets, lineage, retries |
| Quality | Pandera | Data contracts between pipeline stages |
| Vectors | LanceDB | Scene embeddings + similarity search |
| Analytics | DuckDB SQL marts + Streamlit | KPI models and dashboard |

## Quick Start

```bash
# Setup
python -m venv .venv
.venv\Scripts\activate           # Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt

# Run the full pipeline
python run_pipeline.py

# Query the catalog
python -m src.serve --stats
python -m src.serve --event HARD_BRAKE --limit 10

# Launch the dashboard
streamlit run analytics/dashboard.py

# Or use the Dagster DAG UI
dagster dev -m pipeline.definitions
```

## Pipeline Stages

```
[generate] → raw synthetic Parquet
     ↓
[ingest]   → partitioned tracks (Hive: scenario_bucket)
     ↓
[detect]   → partitioned events (Hive: event_type)
     ↓
[featurize]→ kinematic feature vectors
     ↓
[curate]   → balanced subset (dedup + stratified sample)
     ↓
[serve]    → DuckDB CLI + Streamlit dashboard
```

## Dataset

**Default:** Synthetic trajectories via `src/generate.py` — 500 scenarios, 9 agents each, 91 timesteps with injected events.

**Production:** [Waymo Open Motion Dataset](https://waymo.com/open/) — register, download one shard, place in `data/raw/`. The pipeline code is identical.

## Docs

- `docs/system.md` — architecture decisions, tradeoffs, what was left out and why
- `docs/code.md` — per-file purpose, I/O, parameters, data flow diagram
- `docs/errors.md` — error log (error → root cause → fix)
