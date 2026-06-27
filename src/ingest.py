import polars as pl
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq
from pathlib import Path
from src.config import RAW_DIR, TRACKS_DIR, SCENARIO_BUCKET_COUNT
from src.contracts import validate_tracks


def read_raw_shards(raw_dir: Path = RAW_DIR) -> pl.DataFrame:
    parquet_files = list(raw_dir.glob("*.parquet"))
    if not parquet_files:
        raise FileNotFoundError(f"No parquet files in {raw_dir}")
    return pl.concat([pl.read_parquet(f) for f in parquet_files])


def add_partition_key(df: pl.DataFrame, n_buckets: int = SCENARIO_BUCKET_COUNT) -> pl.DataFrame:
    return df.with_columns(
        (pl.col("scenario_id").hash() % n_buckets)
        .cast(pl.Int32)
        .alias("scenario_bucket")
    )


def write_partitioned(df: pl.DataFrame, out_dir: Path = TRACKS_DIR):
    out_dir.mkdir(parents=True, exist_ok=True)
    arrow_table = df.to_arrow()
    ds.write_dataset(
        arrow_table,
        base_dir=str(out_dir),
        format="parquet",
        partitioning=ds.partitioning(
            pa.schema([("scenario_bucket", pa.int32())]),
            flavor="hive",
        ),
        existing_data_behavior="overwrite_or_ignore",
    )


def run():
    print("INGEST: reading raw shards...")
    raw = read_raw_shards()
    print(f"  {len(raw):,} rows from {RAW_DIR}")

    print("INGEST: validating against TrackSchema...")
    validate_tracks(raw)

    print("INGEST: adding partition key...")
    partitioned = add_partition_key(raw)

    print(f"INGEST: writing to {TRACKS_DIR}...")
    write_partitioned(partitioned)

    bucket_counts = partitioned.group_by("scenario_bucket").len().sort("scenario_bucket")
    print(f"  {len(bucket_counts)} buckets, rows per bucket: "
          f"min={bucket_counts['len'].min():,} max={bucket_counts['len'].max():,}")
    print("INGEST: done.")
    return partitioned


if __name__ == "__main__":
    run()
