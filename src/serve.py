import argparse
import duckdb
from src.config import TRACKS_DIR, EVENTS_DIR, CURATED_DIR, FEATURES_PATH


def get_conn() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect()

    conn.execute(f"""
        CREATE VIEW tracks AS
        SELECT * FROM read_parquet('{TRACKS_DIR}/**/*.parquet', hive_partitioning=true)
    """)

    conn.execute(f"""
        CREATE VIEW events AS
        SELECT * FROM read_parquet('{EVENTS_DIR}/**/*.parquet', hive_partitioning=true)
    """)

    curated_path = CURATED_DIR / "curated_tracks.parquet"
    if curated_path.exists():
        conn.execute(f"""
            CREATE VIEW curated AS
            SELECT * FROM read_parquet('{curated_path}')
        """)

    if FEATURES_PATH.exists():
        conn.execute(f"""
            CREATE VIEW features AS
            SELECT * FROM read_parquet('{FEATURES_PATH}')
        """)

    return conn


def query_events(conn, event_type: str = None, limit: int = 20):
    where = f"WHERE event_type = '{event_type}'" if event_type else ""
    sql = f"""
        SELECT scenario_id, object_id, event_type,
               timestep_start, timestep_end,
               ROUND(severity, 3) as severity
        FROM events
        {where}
        ORDER BY severity DESC
        LIMIT {limit}
    """
    return conn.execute(sql).fetchdf()


def query_scenarios(conn, scenario_id: str):
    sql = f"""
        SELECT object_id, object_type, is_ego,
               MIN(timestep) as t_start, MAX(timestep) as t_end,
               ROUND(AVG(SQRT(velocity_x*velocity_x + velocity_y*velocity_y)), 2) as avg_speed
        FROM tracks
        WHERE scenario_id = '{scenario_id}'
        GROUP BY object_id, object_type, is_ego
        ORDER BY is_ego DESC, object_id
    """
    return conn.execute(sql).fetchdf()


def query_stats(conn):
    sql = """
        SELECT
            (SELECT COUNT(DISTINCT scenario_id) FROM tracks) as total_scenarios,
            (SELECT COUNT(*) FROM events) as total_events,
            (SELECT COUNT(DISTINCT scenario_id) FROM events) as scenarios_with_events
    """
    summary = conn.execute(sql).fetchdf()

    event_breakdown = conn.execute("""
        SELECT event_type, COUNT(*) as count,
               ROUND(AVG(severity), 3) as avg_severity,
               ROUND(MAX(severity), 3) as max_severity
        FROM events GROUP BY event_type ORDER BY count DESC
    """).fetchdf()

    return summary, event_breakdown


def run():
    parser = argparse.ArgumentParser(description="Query the AV scenario catalog")
    parser.add_argument("--event", type=str, help="Filter by event type: HARD_BRAKE, CUT_IN, NEAR_MISS")
    parser.add_argument("--scenario", type=str, help="Show details for a specific scenario")
    parser.add_argument("--stats", action="store_true", help="Show catalog statistics")
    parser.add_argument("--sql", type=str, help="Run a raw SQL query")
    parser.add_argument("--limit", type=int, default=20, help="Max rows to return")
    args = parser.parse_args()

    conn = get_conn()

    if args.stats:
        summary, breakdown = query_stats(conn)
        print("\n=== Catalog Summary ===")
        print(summary.to_string(index=False))
        print("\n=== Events by Type ===")
        print(breakdown.to_string(index=False))

    elif args.scenario:
        result = query_scenarios(conn, args.scenario)
        print(f"\n=== Scenario: {args.scenario} ===")
        print(result.to_string(index=False))

    elif args.sql:
        result = conn.execute(args.sql).fetchdf()
        print(result.to_string(index=False))

    else:
        result = query_events(conn, args.event, args.limit)
        print(f"\n=== Events{f' ({args.event})' if args.event else ''} ===")
        print(result.to_string(index=False))

    conn.close()


if __name__ == "__main__":
    run()
