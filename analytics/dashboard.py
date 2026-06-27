import streamlit as st
import duckdb
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WAREHOUSE = PROJECT_ROOT / "data" / "warehouse"
TRACKS_GLOB = str(WAREHOUSE / "tracks" / "**" / "*.parquet")
EVENTS_GLOB = str(WAREHOUSE / "events" / "**" / "*.parquet")
FEATURES_PATH = str(WAREHOUSE / "features.parquet")
CURATED_MANIFEST = str(WAREHOUSE / "curated" / "curated_manifest.parquet")


@st.cache_resource
def get_conn():
    conn = duckdb.connect()
    conn.execute(f"CREATE VIEW tracks AS SELECT * FROM read_parquet('{TRACKS_GLOB}', hive_partitioning=true)")
    conn.execute(f"CREATE VIEW events AS SELECT * FROM read_parquet('{EVENTS_GLOB}', hive_partitioning=true)")
    if Path(FEATURES_PATH).exists():
        conn.execute(f"CREATE VIEW features AS SELECT * FROM read_parquet('{FEATURES_PATH}')")
    if Path(CURATED_MANIFEST).exists():
        conn.execute(f"CREATE VIEW curated_manifest AS SELECT * FROM read_parquet('{CURATED_MANIFEST}')")
    return conn


def query(sql: str) -> pd.DataFrame:
    return get_conn().execute(sql).fetchdf()


st.set_page_config(page_title="AV Scenario Engine", layout="wide")
st.title("AV Scenario Engine — Analytics Dashboard")

col1, col2, col3 = st.columns(3)

summary = query("""
    SELECT
        (SELECT COUNT(DISTINCT scenario_id) FROM tracks) as scenarios,
        (SELECT COUNT(*) FROM events) as events,
        (SELECT COUNT(DISTINCT scenario_id) FROM events) as with_events
""")

col1.metric("Total Scenarios", f"{summary['scenarios'][0]:,}")
col2.metric("Total Events", f"{summary['events'][0]:,}")
col3.metric("Scenarios with Events", f"{summary['with_events'][0]:,}")

st.divider()

left, right = st.columns(2)

with left:
    st.subheader("Events by Type")
    event_freq = query("""
        SELECT event_type, COUNT(*) as count,
               ROUND(AVG(severity), 3) as avg_severity
        FROM events GROUP BY event_type ORDER BY count DESC
    """)
    st.bar_chart(event_freq, x="event_type", y="count")
    st.dataframe(event_freq, use_container_width=True)

with right:
    st.subheader("Severity Distribution")
    severity = query("""
        SELECT event_type,
            CASE
                WHEN severity < 0.2 THEN '0.0-0.2'
                WHEN severity < 0.4 THEN '0.2-0.4'
                WHEN severity < 0.6 THEN '0.4-0.6'
                WHEN severity < 0.8 THEN '0.6-0.8'
                ELSE '0.8-1.0'
            END AS bucket,
            COUNT(*) AS count
        FROM events GROUP BY event_type, bucket
        ORDER BY event_type, bucket
    """)
    st.bar_chart(severity, x="bucket", y="count", color="event_type")

st.divider()

left2, right2 = st.columns(2)

with left2:
    st.subheader("Agent Types")
    agents = query("""
        SELECT object_type, COUNT(DISTINCT object_id) as agents,
               ROUND(AVG(SQRT(velocity_x*velocity_x + velocity_y*velocity_y)), 2) as avg_speed
        FROM tracks WHERE NOT is_ego
        GROUP BY object_type ORDER BY agents DESC
    """)
    st.dataframe(agents, use_container_width=True)

with right2:
    st.subheader("Data Engine Yield")
    if Path(CURATED_MANIFEST).exists():
        yield_data = query("""
            SELECT
                (SELECT COUNT(DISTINCT scenario_id) FROM tracks) as raw,
                (SELECT COUNT(*) FROM curated_manifest) as curated
        """)
        raw_count = yield_data['raw'][0]
        curated_count = yield_data['curated'][0]
        yield_pct = curated_count / max(raw_count, 1) * 100
        st.metric("Yield", f"{yield_pct:.1f}%", delta=f"{curated_count} / {raw_count} scenarios")
    else:
        st.info("Run the curate stage first to see yield metrics.")

st.divider()
st.subheader("Custom Query")
user_sql = st.text_area("SQL", value="SELECT event_type, COUNT(*) FROM events GROUP BY event_type", height=80)
if st.button("Run"):
    try:
        result = query(user_sql)
        st.dataframe(result, use_container_width=True)
    except Exception as e:
        st.error(str(e))
