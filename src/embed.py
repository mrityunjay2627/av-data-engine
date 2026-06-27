import polars as pl
import numpy as np
import lancedb
from sklearn.preprocessing import StandardScaler
from pathlib import Path
from src.config import FEATURES_PATH, LANCE_DIR, EVENTS_DIR


FEATURE_COLS = [
    "mean_speed", "max_speed", "max_decel",
    "trajectory_length", "n_agents", "heading_variance",
]


def read_features(path: Path = FEATURES_PATH) -> pl.DataFrame:
    return pl.read_parquet(path)


def read_events(events_dir: Path = EVENTS_DIR) -> pl.DataFrame:
    try:
        return pl.read_parquet(str(events_dir / "**/*.parquet"), hive_partitioning=True)
    except Exception:
        return pl.DataFrame(schema={"scenario_id": pl.Utf8, "event_type": pl.Utf8})


def build_embeddings(features: pl.DataFrame) -> tuple[np.ndarray, StandardScaler]:
    X = features.select(FEATURE_COLS).to_numpy()
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    norms = np.linalg.norm(X_scaled, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1, norms)
    X_normed = X_scaled / norms
    return X_normed, scaler


def build_table_data(features: pl.DataFrame, embeddings: np.ndarray, events: pl.DataFrame) -> list[dict]:
    event_map = {}
    if not events.is_empty():
        for row in events.iter_rows(named=True):
            sid = row["scenario_id"]
            if sid not in event_map:
                event_map[sid] = []
            event_map[sid].append(row["event_type"])

    records = []
    for i, row in enumerate(features.iter_rows(named=True)):
        sid = row["scenario_id"]
        event_types = event_map.get(sid, [])
        records.append({
            "scenario_id": sid,
            "vector": embeddings[i].tolist(),
            "mean_speed": row["mean_speed"],
            "max_speed": row["max_speed"],
            "max_decel": row["max_decel"],
            "trajectory_length": row["trajectory_length"],
            "n_agents": int(row["n_agents"]),
            "heading_variance": row["heading_variance"],
            "has_event": row["has_event"],
            "event_types": ",".join(sorted(set(event_types))) if event_types else "none",
        })
    return records


def write_to_lancedb(records: list[dict], lance_dir: Path = LANCE_DIR):
    lance_dir.mkdir(parents=True, exist_ok=True)
    db = lancedb.connect(str(lance_dir))
    table = db.create_table("scenarios", data=records, mode="overwrite")
    return table


def search_similar(scenario_id: str, k: int = 5, lance_dir: Path = LANCE_DIR):
    db = lancedb.connect(str(lance_dir))
    table = db.open_table("scenarios")
    target = table.search().where(f"scenario_id = '{scenario_id}'").limit(1).to_pandas()
    if target.empty:
        raise ValueError(f"Scenario {scenario_id} not found")
    query_vector = target.iloc[0]["vector"]
    results = table.search(query_vector).limit(k + 1).to_pandas()
    results = results[results["scenario_id"] != scenario_id].head(k)
    return results


def run():
    print("EMBED: reading features...")
    features = read_features()
    events = read_events()

    print(f"EMBED: building embeddings from {len(FEATURE_COLS)} kinematic features...")
    embeddings, scaler = build_embeddings(features)
    print(f"  embedding shape: {embeddings.shape}")

    print("EMBED: building table records...")
    records = build_table_data(features, embeddings, events)

    print(f"EMBED: writing to LanceDB at {LANCE_DIR}...")
    table = write_to_lancedb(records)
    print(f"  {table.count_rows()} scenarios indexed")

    print("EMBED: testing similarity search...")
    test_id = features["scenario_id"][0]
    similar = search_similar(test_id)
    print(f"  top 3 similar to {test_id}:")
    for _, row in similar.head(3).iterrows():
        print(f"    {row['scenario_id']} (dist={row['_distance']:.4f}, events={row['event_types']})")

    print("EMBED: done.")
    return table


if __name__ == "__main__":
    run()
