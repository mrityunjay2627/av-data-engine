import polars as pl
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from pathlib import Path
from src.config import (
    FEATURES_PATH, EVENTS_DIR, CURATED_DIR, TRACKS_DIR,
    DEDUP_CLUSTER_COUNT, DEDUP_DISTANCE_THRESHOLD,
    CURATED_MAX_PER_EVENT, CURATED_KEEP_ALL_RARE,
)


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


def cluster_and_dedup(features: pl.DataFrame) -> pl.DataFrame:
    X = features.select(FEATURE_COLS).to_numpy()
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    n_clusters = min(DEDUP_CLUSTER_COUNT, len(features))
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = kmeans.fit_predict(X_scaled)

    features = features.with_columns(pl.Series("cluster", labels))

    distances = np.linalg.norm(X_scaled - kmeans.cluster_centers_[labels], axis=1)
    features = features.with_columns(pl.Series("cluster_distance", distances))

    deduped = features.sort("cluster_distance").group_by("cluster").head(
        max(1, len(features) // n_clusters)
    )

    print(f"  dedup: {len(features)} → {len(deduped)} scenarios "
          f"({len(features) - len(deduped)} near-duplicates removed)")

    return deduped


def stratified_sample(features: pl.DataFrame, events: pl.DataFrame) -> pl.DataFrame:
    if events.is_empty():
        return features

    event_scenarios = (
        events.group_by("scenario_id")
        .agg(pl.col("event_type").first().alias("primary_event"))
    )

    labeled = features.join(event_scenarios, on="scenario_id", how="left").with_columns(
        pl.col("primary_event").fill_null("NO_EVENT")
    )

    groups = []
    for event_type in labeled["primary_event"].unique().to_list():
        group = labeled.filter(pl.col("primary_event") == event_type)
        if event_type == "NO_EVENT":
            cap = min(len(group), CURATED_MAX_PER_EVENT)
            groups.append(group.sample(n=cap, seed=42))
        elif CURATED_KEEP_ALL_RARE:
            groups.append(group)
        else:
            cap = min(len(group), CURATED_MAX_PER_EVENT)
            groups.append(group.sample(n=cap, seed=42))

    curated = pl.concat(groups)
    return curated.drop(["primary_event", "cluster", "cluster_distance"])


def write_curated(scenario_ids: list[str], tracks_dir: Path = TRACKS_DIR, out_dir: Path = CURATED_DIR):
    out_dir.mkdir(parents=True, exist_ok=True)
    tracks = pl.read_parquet(str(tracks_dir / "**/*.parquet"), hive_partitioning=True)
    curated_tracks = tracks.filter(pl.col("scenario_id").is_in(scenario_ids))
    curated_tracks.write_parquet(out_dir / "curated_tracks.parquet")
    return curated_tracks


def run():
    print("CURATE: reading features...")
    features = read_features()

    print("CURATE: clustering for dedup...")
    deduped = cluster_and_dedup(features)

    print("CURATE: stratified sampling...")
    events = read_events()
    curated = stratified_sample(deduped, events)

    scenario_ids = curated["scenario_id"].to_list()
    print(f"CURATE: {len(scenario_ids)} scenarios in final curated set")

    print(f"CURATE: writing curated tracks to {CURATED_DIR}...")
    curated_tracks = write_curated(scenario_ids)
    print(f"  {len(curated_tracks):,} track rows in curated set")

    curated.write_parquet(CURATED_DIR / "curated_manifest.parquet")

    yield_pct = len(scenario_ids) / max(features.height, 1)
    print(f"  data engine yield: {yield_pct:.1%} ({len(scenario_ids)}/{features.height})")
    print("CURATE: done.")
    return curated


if __name__ == "__main__":
    run()
