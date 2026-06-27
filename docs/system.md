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

### D2: Storage — Apache Iceberg on Parquet

**Choice:** Iceberg table format, local filesystem catalog.

**Why:** ACID writes, partition pruning, time travel, schema evolution — all the lakehouse primitives, zero cloud cost. DuckDB reads Iceberg natively. If this ever moved to S3, the format doesn't change.

**Tradeoff:** More setup than bare Parquet. Worth it — Iceberg *is* the 2026 standard, and "I used an open table format" is a stronger résumé line than "I wrote Parquet files."

**Partition key — `scenario_id` bucketed into ~100 MB files (not one file per scenario).**

Why not per-scenario? Thousands of tiny files = the classic small-file problem. The OS, DuckDB, and Iceberg all perform better on fewer, larger files. Bucketing by scenario hash gives even file sizes while keeping related trajectories co-located.

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

**Status:** Stretch goal. The pipeline is complete without it.

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
