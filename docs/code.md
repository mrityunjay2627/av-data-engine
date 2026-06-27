# Code Document — AV Scenario Engine

## Directory Map

```
av-scenario-engine/
├─ src/                → Core pipeline logic (one file per stage)
│  ├─ config.py        → All paths, thresholds, tuning knobs
│  ├─ generate.py      → Synthetic trajectory generator
│  ├─ ingest.py        → Raw parquet → partitioned warehouse tracks
│  ├─ contracts.py     → Pandera schemas (data quality gates)
│  ├─ detect.py        → Rule-based event detection
│  ├─ featurize.py     → Per-scenario kinematic features
│  ├─ curate.py        → Dedup + stratified sampling
│  ├─ embed.py         → LanceDB embeddings + similarity search
│  └─ serve.py         → DuckDB CLI query interface
├─ pipeline/           → Dagster orchestration
│  └─ definitions.py   → Asset definitions wiring src/ into a DAG
├─ analytics/          → SQL marts and Streamlit dashboard
│  ├─ marts.sql        → KPI view definitions
│  └─ dashboard.py     → Streamlit app
├─ run_pipeline.py     → One-command full pipeline execution
├─ data/               → All generated data (gitignored)
│  ├─ raw/             → Synthetic or downloaded parquet shards
│  ├─ warehouse/       → Partitioned tables (tracks, events, curated)
│  │  ├─ tracks/       → Hive-partitioned by scenario_bucket
│  │  ├─ events/       → Hive-partitioned by event_type
│  │  ├─ curated/      → Curated tracks + manifest
│  │  └─ features.parquet
│  └─ lance/           → LanceDB vector store (stretch)
├─ tests/              → Validation and smoke tests
├─ docs/               → This file, system.md, errors.md
└─ README.md
```

---

## File Reference

### run_pipeline.py
**Purpose:** One-command runner that executes all five stages sequentially.
**Run:** `python run_pipeline.py`

### src/config.py
**Purpose:** Single source of truth for paths, thresholds, partition settings, generation params, and curation knobs.
**Input:** None (constants).
**Output:** Importable by all other src/ files.

Key parameters:
- `HARD_BRAKE_THRESHOLD_MS2 = -4.0` — deceleration below this triggers a hard-brake event
- `CUT_IN_DISTANCE_M = 5.0` — lateral proximity threshold for cut-in detection
- `NEAR_MISS_GAP_M = 2.0` — minimum ego-agent distance for near-miss
- `SCENARIO_BUCKET_COUNT = 32` — number of Hive partition buckets for tracks
- `DEDUP_CLUSTER_COUNT = 50` — KMeans clusters for redundancy removal
- `CURATED_MAX_PER_EVENT = 80` — cap per event type in final curated set

### src/generate.py
**Purpose:** Synthetic trajectory generator. Creates ego + agent tracks with intentional event injection (hard brakes ~15%, cut-ins ~10%).
**Input:** Generation params from config.
**Output:** `data/raw/synthetic_shard_000.parquet`
**Run:** `python -m src.generate`

### src/contracts.py
**Purpose:** Pandera DataFrameModel schemas defining data contracts between stages.
**Input:** None (schema definitions).
**Output:** `validate_tracks()`, `validate_events()`, `validate_features()` — called by each stage before writing.

Contracts enforced:
- TrackSchema: valid object types, non-negative timesteps, heading in [-π, π], positive dimensions
- EventSchema: valid event types, severity in [0, 1]
- FeatureSchema: non-negative speeds, trajectory lengths

### src/ingest.py
**Purpose:** Read raw parquet shards, validate, add partition key (scenario_bucket), write Hive-partitioned Parquet.
**Input:** `data/raw/*.parquet`
**Output:** `data/warehouse/tracks/scenario_bucket=N/*.parquet`

Key operation: `scenario_bucket = hash(scenario_id) % 32` — bucketing avoids the small-file problem (one file per scenario = thousands of tiny files).

### src/detect.py
**Purpose:** Read tracks, compute acceleration from velocity diffs, detect three event types.
**Input:** `data/warehouse/tracks/`
**Output:** `data/warehouse/events/event_type=X/*.parquet`

Detection rules:
- **HARD_BRAKE:** ego deceleration < -4.0 m/s² (velocity diff / dt)
- **CUT_IN:** non-ego agent within 5m lateral + 15m longitudinal of ego
- **NEAR_MISS:** ego-agent Euclidean distance < 2.0m

Severity scoring: normalized 0-1 based on how far past the threshold.

### src/featurize.py
**Purpose:** Compute per-scenario kinematic feature vector from ego track.
**Input:** Tracks table + events table.
**Output:** `data/warehouse/features.parquet`

Feature vector: mean_speed, max_speed, max_decel, trajectory_length, n_agents, heading_variance, has_event.

### src/curate.py
**Purpose:** Cluster scenes by kinematic similarity, remove near-duplicates, stratified sample to balance rare/common events.
**Input:** Features + events tables.
**Output:** `data/warehouse/curated/curated_tracks.parquet` + `curated_manifest.parquet`

Algorithm:
1. StandardScaler on feature columns
2. KMeans clustering (50 clusters)
3. Keep closest-to-centroid within each cluster (dedup)
4. Stratified sample: keep all rare-event scenarios, cap NO_EVENT at 80

### src/serve.py
**Purpose:** DuckDB-powered CLI to query the catalog.
**Input:** User query via argparse.
**Output:** Printed results.
**Run:**
- `python -m src.serve --stats` — catalog summary
- `python -m src.serve --event HARD_BRAKE` — filter by event type
- `python -m src.serve --scenario sc_00042` — scenario details
- `python -m src.serve --similar sc_00042` — find similar via LanceDB
- `python -m src.serve --sql "SELECT ..."` — raw SQL

### src/embed.py
**Purpose:** Build normalized kinematic embeddings and index them in LanceDB for similarity search.
**Input:** `data/warehouse/features.parquet` + events table.
**Output:** `data/lance/scenarios.lance/` (LanceDB table).
**Run:** `python -m src.embed`

Algorithm:
1. StandardScaler on 6 kinematic features
2. L2-normalize to unit vectors
3. Store in LanceDB with metadata (event types, speed stats)
4. Similarity search via cosine distance on the normalized vectors

### tests/test_pipeline.py
**Purpose:** Smoke tests covering data generation, contract validation, event detection, dedup, and full pipeline integration.
**Run:** `python -m tests.test_pipeline`

Tests:
- `test_generate` — correct row count, scenario count, object types, ego presence
- `test_contracts_valid` — valid data passes Pandera schemas
- `test_contracts_reject_bad_data` — invalid event types are caught
- `test_detect_hard_brake` — synthetic hard brake is detected
- `test_detect_no_false_positives` — constant-speed track produces zero events
- `test_curate_dedup_reduces` — clustering removes near-duplicates
- `test_full_pipeline_smoke` — end-to-end generate→ingest→detect→featurize

### pipeline/definitions.py
**Purpose:** Dagster software-defined assets wiring src/ stages into a DAG.
**Run:** `dagster dev -m pipeline.definitions`

Asset dependency chain: tracks → events → features → curated.
Each asset reports metadata (row counts, paths) visible in the Dagster UI.

### analytics/marts.sql
**Purpose:** SQL view definitions for KPI models.
**Input:** DuckDB views over warehouse tables.

Models:
- `mart_event_frequency` — count, avg/max severity by event type
- `mart_severity_distribution` — severity histogram buckets
- `mart_agent_types` — agent type breakdown with avg speed
- `mart_data_engine_yield` — raw vs curated scenario count
- `mart_scenario_complexity` — most complex scenarios by event count

### analytics/dashboard.py
**Purpose:** Streamlit dashboard rendering mart KPIs as charts.
**Run:** `streamlit run analytics/dashboard.py`

Panels: summary metrics, event frequency bar chart, severity distribution, agent type table, data engine yield, custom SQL query box.

---

## Data Flow

```
[generate.py] ──────────▶ data/raw/ (synthetic Parquet)
    │                       ↕ (swap real WOMD later)
    ▼
[ingest.py] ──contracts──▶ data/warehouse/tracks/ (Hive-partitioned)
    │
    ▼
[detect.py] ──contracts──▶ data/warehouse/events/ (Hive-partitioned)
    │
    ├──▶ [featurize.py] ──contracts──▶ data/warehouse/features.parquet
    │         │
    │         ├──▶ [embed.py] ────────────▶ data/lance/ (LanceDB)
    │         │
    │         ▼
    └──▶ [curate.py] ────────────────▶ data/warehouse/curated/
              │
              ├──▶ [serve.py]             DuckDB CLI
              └──▶ [dashboard.py]         Streamlit
                     │
                     └── marts.sql        KPI views
```
