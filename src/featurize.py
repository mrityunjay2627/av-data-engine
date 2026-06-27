import polars as pl
from pathlib import Path
from src.config import TRACKS_DIR, EVENTS_DIR, FEATURES_PATH
from src.contracts import validate_features


def read_tracks(tracks_dir: Path = TRACKS_DIR) -> pl.DataFrame:
    return pl.read_parquet(str(tracks_dir / "**/*.parquet"), hive_partitioning=True)


def read_events(events_dir: Path = EVENTS_DIR) -> pl.DataFrame:
    path = str(events_dir / "**/*.parquet")
    try:
        return pl.read_parquet(path, hive_partitioning=True)
    except Exception:
        return pl.DataFrame(schema={"scenario_id": pl.Utf8, "event_type": pl.Utf8})


def compute_ego_features(tracks: pl.DataFrame) -> pl.DataFrame:
    ego = tracks.filter(pl.col("is_ego"))

    ego = ego.with_columns(
        (pl.col("velocity_x").pow(2) + pl.col("velocity_y").pow(2))
        .sqrt()
        .alias("speed")
    ).sort(["scenario_id", "object_id", "timestep"]).with_columns(
        pl.col("speed")
        .diff()
        .over(["scenario_id", "object_id"])
        .truediv(0.1)
        .alias("accel")
    )

    ego = ego.with_columns([
        (pl.col("position_x").diff().over(["scenario_id", "object_id"]).pow(2)
         + pl.col("position_y").diff().over(["scenario_id", "object_id"]).pow(2))
        .sqrt()
        .alias("step_dist")
    ])

    features = ego.group_by("scenario_id").agg([
        pl.col("speed").mean().alias("mean_speed"),
        pl.col("speed").max().alias("max_speed"),
        pl.col("accel").min().alias("max_decel"),
        pl.col("step_dist").sum().alias("trajectory_length"),
        pl.col("heading").var().alias("heading_variance"),
    ])

    return features


def add_agent_count(features: pl.DataFrame, tracks: pl.DataFrame) -> pl.DataFrame:
    agent_counts = (
        tracks.group_by("scenario_id")
        .agg(pl.col("object_id").n_unique().alias("n_agents"))
    )
    return features.join(agent_counts, on="scenario_id", how="left")


def add_event_flag(features: pl.DataFrame, events: pl.DataFrame) -> pl.DataFrame:
    if events.is_empty():
        return features.with_columns(pl.lit(False).alias("has_event"))

    event_scenarios = events.select("scenario_id").unique()
    return features.with_columns(
        pl.col("scenario_id")
        .is_in(event_scenarios["scenario_id"])
        .alias("has_event")
    )


def run():
    print("FEATURIZE: reading tracks...")
    tracks = read_tracks()

    print("FEATURIZE: computing ego kinematic features...")
    features = compute_ego_features(tracks)

    print("FEATURIZE: adding agent counts...")
    features = add_agent_count(features, tracks)

    print("FEATURIZE: adding event flags...")
    events = read_events()
    features = add_event_flag(features, events)

    features = features.with_columns([
        pl.col("max_decel").fill_null(0.0),
        pl.col("heading_variance").fill_null(0.0),
        pl.col("n_agents").cast(pl.Int64),
    ])

    print("FEATURIZE: validating against FeatureSchema...")
    validate_features(features)

    FEATURES_PATH.parent.mkdir(parents=True, exist_ok=True)
    features.write_parquet(FEATURES_PATH)
    print(f"  {len(features)} scenario feature vectors → {FEATURES_PATH}")

    event_rate = features.filter(pl.col("has_event")).height / max(features.height, 1)
    print(f"  event rate: {event_rate:.1%}")
    print("FEATURIZE: done.")
    return features


if __name__ == "__main__":
    run()
