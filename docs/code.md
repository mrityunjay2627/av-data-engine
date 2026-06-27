# Code Document — AV Scenario Engine

## Directory Map

```
av-scenario-engine/
├─ src/              → Core pipeline logic (one file per stage)
├─ pipeline/         → Dagster orchestration (wires src/ into a DAG)
├─ analytics/        → SQL marts and Streamlit dashboard
├─ data/             → All generated data (gitignored)
│  ├─ raw/           → Downloaded WOMD proto shards
│  ├─ warehouse/     → Iceberg tables (tracks, events)
│  └─ lance/         → LanceDB vector store (stretch)
├─ tests/            → Validation and smoke tests
├─ docs/             → This file, system.md, errors.md
└─ README.md
```

---

## File Reference

### src/config.py
**Purpose:** Single source of truth for paths, thresholds, and partition settings.
**Input:** None (constants).
**Output:** Importable config object used by all other src/ files.

### src/generate.py
**Purpose:** Synthetic trajectory generator producing data in the WOMD schema. Creates ego + agent tracks with intentional event injection (hard brakes, cut-ins) for pipeline validation.
**Input:** Generation parameters from config (scenario count, timesteps, agents per scenario).
**Output:** `data/raw/synthetic_shard_000.parquet` — raw trajectories ready for ingest.
**Run:** `python -m src.generate`

### src/ingest.py
**Purpose:** Parse one WOMD protobuf shard → write Iceberg `tracks` table.
**Input:** `data/raw/*.tfrecord` (Waymo proto shard).
**Output:** `data/warehouse/tracks/` (Iceberg table, partitioned by scenario bucket).

### src/detect.py
**Purpose:** Read tracks, apply rule-based event detection (hard brake, cut-in, near-miss).
**Input:** Iceberg `tracks` table.
**Output:** `data/warehouse/events/` (Iceberg table, partitioned by event_type).

### src/featurize.py
**Purpose:** Compute per-scene kinematic feature vector for dedup and similarity.
**Input:** Iceberg `tracks` table.
**Output:** Feature matrix (Parquet or LanceDB table).

### src/curate.py
**Purpose:** Cluster scenes, remove near-duplicates, stratified sample for balance.
**Input:** Feature matrix + events table.
**Output:** `data/warehouse/curated/` — the final balanced scenario set.

### src/contracts.py
**Purpose:** Pandera schemas defining data contracts between stages.
**Input:** None (schema definitions).
**Output:** Importable validators called by each stage before writing.

### src/serve.py
**Purpose:** DuckDB-powered CLI to query the curated catalog.
**Input:** User query (event type, conditions, limit).
**Output:** Matching scenarios printed to stdout.

### pipeline/definitions.py
**Purpose:** Dagster asset definitions wiring src/ stages into an orchestrated DAG.
**Input:** Dagster runtime.
**Output:** Materialized assets with lineage visible in Dagster UI.

### analytics/marts.sql
**Purpose:** SQL models computing KPIs over the warehouse tables.
**Input:** Iceberg tracks + events tables (via DuckDB).
**Output:** Queryable views (event frequency, severity, dedup ratio, yield).

### analytics/dashboard.py
**Purpose:** Streamlit app rendering the mart KPIs as charts.
**Input:** DuckDB views from marts.sql.
**Output:** Browser dashboard.

---

## Data Flow

```
[generate.py] ──────────▶ data/raw/ (synthetic Parquet)
    │                       ↕ (swap real WOMD later)
    ▼
WOMD .tfrecord or synthetic .parquet
    │
    ▼
[ingest.py] ──contracts──▶ Iceberg: tracks
    │
    ▼
[detect.py] ──contracts──▶ Iceberg: events
    │
    ▼
[featurize.py] ──────────▶ feature matrix
    │
    ▼
[curate.py] ─────────────▶ Iceberg: curated
    │
    ├──▶ [serve.py]         CLI queries
    └──▶ [marts.sql]        KPI views
           │
           ▼
         [dashboard.py]     Streamlit
```
