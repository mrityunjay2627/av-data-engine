from dagster import (
    asset, Definitions, AssetExecutionContext,
    MaterializeResult, MetadataValue,
)
from src.config import TRACKS_DIR, EVENTS_DIR, FEATURES_PATH, CURATED_DIR


@asset(group_name="scenario_engine", description="Ingest raw parquet shards into partitioned tracks table")
def tracks(context: AssetExecutionContext) -> MaterializeResult:
    from src.ingest import run
    df = run()
    return MaterializeResult(
        metadata={
            "row_count": MetadataValue.int(len(df)),
            "scenario_count": MetadataValue.int(df["scenario_id"].n_unique()),
            "output_dir": MetadataValue.path(str(TRACKS_DIR)),
        }
    )


@asset(
    group_name="scenario_engine",
    deps=[tracks],
    description="Detect safety events (hard brakes, cut-ins, near-misses) from tracks",
)
def events(context: AssetExecutionContext) -> MaterializeResult:
    from src.detect import run
    df = run()
    return MaterializeResult(
        metadata={
            "event_count": MetadataValue.int(len(df)),
            "output_dir": MetadataValue.path(str(EVENTS_DIR)),
        }
    )


@asset(
    group_name="scenario_engine",
    deps=[tracks, events],
    description="Compute per-scenario kinematic feature vectors",
)
def features(context: AssetExecutionContext) -> MaterializeResult:
    from src.featurize import run
    df = run()
    return MaterializeResult(
        metadata={
            "feature_count": MetadataValue.int(len(df)),
            "event_rate": MetadataValue.float(
                df.filter(df["has_event"]).height / max(df.height, 1)
            ),
            "output_path": MetadataValue.path(str(FEATURES_PATH)),
        }
    )


@asset(
    group_name="scenario_engine",
    deps=[features, events],
    description="Deduplicate and curate a balanced scenario set",
)
def curated(context: AssetExecutionContext) -> MaterializeResult:
    from src.curate import run
    df = run()
    return MaterializeResult(
        metadata={
            "curated_scenarios": MetadataValue.int(len(df)),
            "output_dir": MetadataValue.path(str(CURATED_DIR)),
        }
    )


defs = Definitions(assets=[tracks, events, features, curated])
