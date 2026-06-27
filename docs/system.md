# System Document — AV Scenario Engine

## 1. Project Purpose

AV fleets collect orders of magnitude more driving data than anyone can label. ~99% is boring (empty highway, straight roads). The real engineering problem is finding and curating the interesting 1%: hard brakes, cut-ins, near-misses.

This project builds that **data engine**: ingest → detect → featurize → curate → serve.

The AI stays deliberately small (rule-based event detection, pretrained embeddings). The value lives in the architecture and data engineering.

---

## 2. Design Philosophy

**"Design for scale, run on a sample."**

Every architectural choice is Spark-swappable, cloud-portable, and uses open formats — but we run single-node on one Waymo shard because scale without substance is cargo cult.

---

## 3. Architecture Decisions

### D1: Dataset — Waymo Open Motion Dataset (WOMD)

**Choice:** Motion trajectories, not Perception (camera/LiDAR).

**Why:** Event detection becomes clean math over tracks (velocity, acceleration, inter-agent distance) — no image models, no GPU decode. One shard (~500 scenes) is enough to prove the pipeline.

**Tradeoff:** We lose the ability to embed visual frames. If we add LanceDB, embeddings will be kinematic features, not images.

---

### D2: Storage — Hive-Partitioned Parquet (Iceberg-ready)

**Choice:** Hive-style partitioned Parquet on local filesystem, queried by DuckDB with automatic partition pruning.

**Why:** This is the exact physical layout Iceberg uses underneath. We get the core concepts — partitioned columnar storage, predicate pushdown, partition pruning — without fighting catalog setup on Windows. DuckDB reads Hive-partitioned Parquet natively with `hive_partitioning=true`.

**Iceberg upgrade path:** Adding Iceberg is a catalog-layer config change (PyIceberg SqlCatalog + SQLite), not a rewrite. The Parquet files don't move. This gets you ACID transactions, schema evolution, and time travel — defer until you need multi-writer concurrency or snapshots.

**Tradeoff:** No ACID writes, no time travel, no schema evolution without Iceberg. Acceptable for a single-writer pipeline on local disk.

**Partition key — `scenario_bucket` (hash of scenario_id % 32) for tracks; `event_type` for events.**

Why not per-scenario? Thousands of tiny files = the classic small-file problem. The OS, DuckDB, and any future Spark all perform better on fewer, larger files. Bucketing by scenario hash gives even file sizes while keeping related trajectories co-located. Events partition by type because the dominant query is "give me all cut-ins" — that reads one partition directory.

---

### D3: Transform — Polars (not Spark, not pandas)

**Choice:** Polars with lazy evaluation.

**Why:** Streaming-capable, out-of-core, Arrow-native. At sample scale, Spark's JVM overhead and cluster setup cost more time than they save. Polars' lazy API mirrors Spark's logical plan model, so the thinking transfers.

**Tradeoff:** Less name recognition than Spark on a résumé. Mitigated by articulating *why* — "I chose the right tool for the data volume" is the senior answer.

---

### D4: Query — DuckDB

**Choice:** In-process OLAP engine for both ad-hoc queries and the serving CLI.

**Why:** Native Parquet and Iceberg reads, predicate pushdown, partition pruning — warehouse-grade query on local files. Zero server process.

---

### D5: Orchestration — Dagster

**Choice:** Dagster software-defined assets.

**Why:** Each pipeline stage becomes an asset with typed I/O, lineage, and retry logic. The Dagster UI gives a DAG view, run history, and materialization status — turns scripts into a system.

**Tradeoff:** Heavier dependency than a Makefile or shell script. Justified because orchestration is the single most-asked-about infra skill in data engineering interviews.

---

### D6: Quality — Pandera data contracts

**Choice:** Schema validation between every pipeline stage.

**Why:** Catches silent corruption (negative speeds, duplicate scenario IDs, null coordinates) before it propagates. Data contracts are a named 2026 practice.

---

### D7: Analytics — SQL marts + Streamlit

**Choice:** DuckDB SQL views as a semantic layer; Streamlit dashboard.

**Why:** KPI models (event frequency, severity distribution, dedup ratio, data-engine yield) belong in SQL — reproducible, versionable, queryable. Streamlit wraps them with zero frontend overhead.

---

### D8: Vectors — LanceDB (stretch)

**Choice:** LanceDB for scene embeddings and similarity search.

**Why:** "Find more scenes like this" is a real AV data-engine capability. LanceDB is purpose-built for multimodal embeddings alongside tabular data.

**Status:** Implemented. Embeddings are L2-normalized 6D kinematic vectors stored in LanceDB.

---

### D9: Synthetic data generator — decouple dev from data access

**Choice:** Build a trajectory generator that produces data in the same schema as WOMD. Develop and test the full pipeline on synthetic data; swap in real Waymo data later via a thin adapter.

**Why:** The `waymo-open-dataset` decode package is Linux-only (no Windows support). Rather than block pipeline development on data access, generate realistic trajectories with intentional event injection (hard brakes, cut-ins) so detection logic can be validated immediately. This is standard practice in data engineering — test on synthetic, validate on real.

**Tradeoff:** Synthetic trajectories lack the complexity of real driving (no map context, simplified kinematics). Acceptable because the pipeline's value is in the architecture, not the model accuracy.

---

## 4. What We Deliberately Left Out (and Why)

| Tool | Why not |
|------|---------|
| Spark | Overhead exceeds data volume. The architecture is Spark-swappable if volume grew. |
| Kafka / Flink | No real-time stream source. Simulating one is theatre. |
| Kubernetes | Single-node pipeline. Container orchestration solves a problem we don't have. |
| dbt | DuckDB SQL views achieve the same mart layer without another dependency. |
| GPU / deep learning | Event detection is rule-based. No labels exist for a supervised model. |

---

## 5. Decision Log

| # | Date | Decision | Rationale |
|---|------|----------|-----------|
| 1 | 2026-06-26 | Use WOMD not Perception | Trajectory math > image decode for this scope |
| 2 | 2026-06-26 | Iceberg over bare Parquet | Lakehouse primitives, résumé signal, DuckDB compat |
| 3 | 2026-06-26 | Polars over Spark | Right-sized for volume; lazy API teaches the same planning concepts |
| 4 | 2026-06-26 | Dagster for orchestration | Asset model maps to lakehouse tables; interview-relevant |
| 5 | 2026-06-26 | LanceDB as stretch | Vectors are optional; core pipeline works without it |
| 6 | 2026-06-27 | Synthetic data generator | Decouples pipeline dev from data access; swap real Waymo later |
| 7 | 2026-06-27 | LanceDB implemented | Kinematic embeddings + similarity search via normalized vectors |
| 8 | 2026-06-27 | Hive-partitioned Parquet over full Iceberg | Same physical layout; defer catalog layer until multi-writer needed |
