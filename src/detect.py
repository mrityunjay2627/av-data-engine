import polars as pl
import pyarrow as pa
import pyarrow.dataset as ds
from pathlib import Path
from src.config import (
    TRACKS_DIR, EVENTS_DIR,
    HARD_BRAKE_THRESHOLD_MS2, CUT_IN_DISTANCE_M, NEAR_MISS_GAP_M,
)
from src.contracts import validate_events


def read_tracks(tracks_dir: Path = TRACKS_DIR) -> pl.DataFrame:
    return pl.read_parquet(
        str(tracks_dir / "**/*.parquet"),
        hive_partitioning=True,
    )


def compute_speed_and_accel(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns([
        (pl.col("velocity_x").pow(2) + pl.col("velocity_y").pow(2))
        .sqrt()
        .alias("speed"),
    ]).sort(["scenario_id", "object_id", "timestep"]).with_columns(
        pl.col("speed")
        .diff()
        .over(["scenario_id", "object_id"])
        .truediv(0.1)
        .alias("accel_ms2")
    )


def detect_hard_brakes(df: pl.DataFrame) -> pl.DataFrame:
    ego = df.filter(pl.col("is_ego"))
    braking = ego.filter(pl.col("accel_ms2") < HARD_BRAKE_THRESHOLD_MS2)
    if braking.is_empty():
        return pl.DataFrame(schema={
            "scenario_id": pl.Utf8, "object_id": pl.Utf8,
            "event_type": pl.Utf8, "timestep_start": pl.Int64,
            "timestep_end": pl.Int64, "severity": pl.Float64,
        })

    events = braking.group_by(["scenario_id", "object_id"]).agg([
        pl.col("timestep").min().alias("timestep_start"),
        pl.col("timestep").max().alias("timestep_end"),
        (pl.col("accel_ms2").min().abs() / 10.0).clip(0.0, 1.0).alias("severity"),
    ]).with_columns(pl.lit("HARD_BRAKE").alias("event_type"))

    return events


def detect_cut_ins(df: pl.DataFrame) -> pl.DataFrame:
    ego = df.filter(pl.col("is_ego")).select([
        "scenario_id", "timestep",
        pl.col("position_x").alias("ego_x"),
        pl.col("position_y").alias("ego_y"),
    ])

    agents = df.filter(~pl.col("is_ego"))

    joined = agents.join(ego, on=["scenario_id", "timestep"], how="inner")

    joined = joined.with_columns([
        (pl.col("position_x") - pl.col("ego_x")).abs().alias("dx"),
        (pl.col("position_y") - pl.col("ego_y")).abs().alias("dy"),
    ])

    close = joined.filter(
        (pl.col("dx") < CUT_IN_DISTANCE_M * 3) & (pl.col("dy") < CUT_IN_DISTANCE_M)
    )

    if close.is_empty():
        return pl.DataFrame(schema={
            "scenario_id": pl.Utf8, "object_id": pl.Utf8,
            "event_type": pl.Utf8, "timestep_start": pl.Int64,
            "timestep_end": pl.Int64, "severity": pl.Float64,
        })

    events = close.group_by(["scenario_id", "object_id"]).agg([
        pl.col("timestep").min().alias("timestep_start"),
        pl.col("timestep").max().alias("timestep_end"),
        (1.0 - pl.col("dy").min() / CUT_IN_DISTANCE_M).clip(0.0, 1.0).alias("severity"),
    ]).with_columns(pl.lit("CUT_IN").alias("event_type"))

    return events


def detect_near_misses(df: pl.DataFrame) -> pl.DataFrame:
    ego = df.filter(pl.col("is_ego")).select([
        "scenario_id", "timestep",
        pl.col("position_x").alias("ego_x"),
        pl.col("position_y").alias("ego_y"),
    ])

    agents = df.filter(~pl.col("is_ego"))
    joined = agents.join(ego, on=["scenario_id", "timestep"], how="inner")

    joined = joined.with_columns(
        ((pl.col("position_x") - pl.col("ego_x")).pow(2)
         + (pl.col("position_y") - pl.col("ego_y")).pow(2))
        .sqrt()
        .alias("distance")
    )

    close = joined.filter(pl.col("distance") < NEAR_MISS_GAP_M)

    if close.is_empty():
        return pl.DataFrame(schema={
            "scenario_id": pl.Utf8, "object_id": pl.Utf8,
            "event_type": pl.Utf8, "timestep_start": pl.Int64,
            "timestep_end": pl.Int64, "severity": pl.Float64,
        })

    events = close.group_by(["scenario_id", "object_id"]).agg([
        pl.col("timestep").min().alias("timestep_start"),
        pl.col("timestep").max().alias("timestep_end"),
        (1.0 - pl.col("distance").min() / NEAR_MISS_GAP_M).clip(0.0, 1.0).alias("severity"),
    ]).with_columns(pl.lit("NEAR_MISS").alias("event_type"))

    return events


def write_events(events: pl.DataFrame, out_dir: Path = EVENTS_DIR):
    out_dir.mkdir(parents=True, exist_ok=True)
    arrow_table = events.to_arrow()
    ds.write_dataset(
        arrow_table,
        base_dir=str(out_dir),
        format="parquet",
        partitioning=ds.partitioning(
            pa.schema([("event_type", pa.string())]),
            flavor="hive",
        ),
        existing_data_behavior="overwrite_or_ignore",
    )


def run():
    print("DETECT: reading tracks...")
    tracks = read_tracks()
    tracks = compute_speed_and_accel(tracks)
    print(f"  {tracks['scenario_id'].n_unique()} scenarios loaded")

    print("DETECT: finding hard brakes...")
    hb = detect_hard_brakes(tracks)
    print(f"  {len(hb)} hard brake events")

    print("DETECT: finding cut-ins...")
    ci = detect_cut_ins(tracks)
    print(f"  {len(ci)} cut-in events")

    print("DETECT: finding near-misses...")
    nm = detect_near_misses(tracks)
    print(f"  {len(nm)} near-miss events")

    all_events = pl.concat([hb, ci, nm])
    print(f"DETECT: {len(all_events)} total events")

    if not all_events.is_empty():
        print("DETECT: validating against EventSchema...")
        validate_events(all_events)

        print(f"DETECT: writing to {EVENTS_DIR}...")
        write_events(all_events)

    print("DETECT: done.")
    return all_events


if __name__ == "__main__":
    run()
