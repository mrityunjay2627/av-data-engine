# AV Scenario Engine

A scenario-mining and curation pipeline for autonomous vehicle driving logs.

Ingests Waymo Open Motion Dataset trajectories, detects safety-relevant driving events (hard brakes, cut-ins, near-misses), deduplicates and curates a balanced training subset, and serves it as a queryable catalog — the "data engine" loop that feeds AV perception and planning models.

## Architecture

**Single-node lakehouse** — designed for scale, demonstrated on a sample.

| Layer | Tool | Why |
|-------|------|-----|
| Storage | Apache Iceberg on Parquet | Open table format: ACID, time travel, partition pruning |
| Transform | Polars | Streaming-capable DataFrame engine, no Spark overhead |
| Query | DuckDB | In-process OLAP, native Iceberg reads |
| Orchestration | Dagster | Software-defined assets, lineage, retries |
| Quality | Pandera | Data contracts between pipeline stages |
| Vectors | LanceDB | Scene embeddings + similarity search (stretch) |
| Analytics | DuckDB SQL marts + Streamlit | KPI models and dashboard |

## Pipeline Stages

```
WOMD Proto → [ingest] → Iceberg tracks
                          ↓
                      [detect] → Iceberg events
                          ↓
                      [featurize] → kinematic vectors
                          ↓
                      [curate] → balanced subset
                          ↓
                      [serve] → DuckDB CLI / Streamlit dashboard
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Dataset

[Waymo Open Motion Dataset](https://waymo.com/open/) — register for access, download one training shard to `data/raw/`.

## Docs

- `docs/system.md` — architecture decisions and tradeoffs
- `docs/code.md` — per-file / per-directory purpose and I/O
- `docs/errors.md` — error log (error → root cause → fix)
