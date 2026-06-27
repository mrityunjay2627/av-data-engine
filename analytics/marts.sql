-- =================================================================
-- KPI Mart Models for AV Scenario Engine
-- Run via DuckDB: duckdb < analytics/marts.sql
-- Or loaded by dashboard.py
-- =================================================================

-- Paths are set by the calling script via SET VARIABLE or string replacement.
-- When run standalone, override these:
-- SET VARIABLE tracks_path = 'data/warehouse/tracks/**/*.parquet';
-- SET VARIABLE events_path = 'data/warehouse/events/**/*.parquet';
-- SET VARIABLE features_path = 'data/warehouse/features.parquet';
-- SET VARIABLE curated_path = 'data/warehouse/curated/curated_manifest.parquet';


-- M1: Event frequency by type
CREATE OR REPLACE VIEW mart_event_frequency AS
SELECT
    event_type,
    COUNT(*) AS event_count,
    COUNT(DISTINCT scenario_id) AS scenarios_affected,
    ROUND(AVG(severity), 3) AS avg_severity,
    ROUND(MAX(severity), 3) AS max_severity,
    ROUND(MIN(severity), 3) AS min_severity
FROM events
GROUP BY event_type
ORDER BY event_count DESC;


-- M2: Severity distribution (histogram buckets)
CREATE OR REPLACE VIEW mart_severity_distribution AS
SELECT
    event_type,
    CASE
        WHEN severity < 0.2 THEN '0.0-0.2'
        WHEN severity < 0.4 THEN '0.2-0.4'
        WHEN severity < 0.6 THEN '0.4-0.6'
        WHEN severity < 0.8 THEN '0.6-0.8'
        ELSE '0.8-1.0'
    END AS severity_bucket,
    COUNT(*) AS count
FROM events
GROUP BY event_type, severity_bucket
ORDER BY event_type, severity_bucket;


-- M3: Agent type breakdown across all scenarios
CREATE OR REPLACE VIEW mart_agent_types AS
SELECT
    object_type,
    COUNT(DISTINCT object_id) AS unique_agents,
    COUNT(DISTINCT scenario_id) AS scenarios_present,
    ROUND(AVG(SQRT(velocity_x*velocity_x + velocity_y*velocity_y)), 2) AS avg_speed
FROM tracks
WHERE NOT is_ego
GROUP BY object_type
ORDER BY unique_agents DESC;


-- M4: Data engine yield — raw vs curated
CREATE OR REPLACE VIEW mart_data_engine_yield AS
SELECT
    (SELECT COUNT(DISTINCT scenario_id) FROM tracks) AS total_scenarios,
    (SELECT COUNT(DISTINCT scenario_id) FROM features) AS featurized,
    (SELECT COUNT(*) FROM curated_manifest) AS curated_count,
    ROUND(
        (SELECT COUNT(*) FROM curated_manifest) * 100.0
        / NULLIF((SELECT COUNT(DISTINCT scenario_id) FROM tracks), 0),
        1
    ) AS yield_pct;


-- M5: Scenario complexity — events per scenario
CREATE OR REPLACE VIEW mart_scenario_complexity AS
SELECT
    scenario_id,
    COUNT(*) AS event_count,
    COUNT(DISTINCT event_type) AS event_types,
    ROUND(MAX(severity), 3) AS worst_severity
FROM events
GROUP BY scenario_id
ORDER BY event_count DESC
LIMIT 50;
