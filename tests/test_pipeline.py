import polars as pl
import numpy as np
from pathlib import Path
from src.config import (
    RAW_DIR, TRACKS_DIR, EVENTS_DIR, FEATURES_PATH, CURATED_DIR, LANCE_DIR,
    HARD_BRAKE_THRESHOLD_MS2, CUT_IN_DISTANCE_M, NEAR_MISS_GAP_M,
)


def test_generate():
    from src.generate import generate_scenarios
    df = generate_scenarios(n_scenarios=10, n_timesteps=20, n_agents=3, seed=99)
    assert df.shape[0] == 10 * 20 * (1 + 3)
    assert df["scenario_id"].n_unique() == 10
    assert set(df["object_type"].unique().to_list()).issubset({"VEHICLE", "PEDESTRIAN", "CYCLIST"})
    ego_count = df.filter(pl.col("is_ego")).height
    assert ego_count == 10 * 20
    print("PASS: test_generate")


def test_contracts_valid():
    from src.contracts import validate_tracks, validate_events, validate_features
    from src.generate import generate_scenarios

    tracks = generate_scenarios(n_scenarios=5, n_timesteps=10, n_agents=2, seed=1)
    validate_tracks(tracks)

    events = pl.DataFrame({
        "scenario_id": ["sc_00000"],
        "object_id": ["sc_00000_ego"],
        "event_type": ["HARD_BRAKE"],
        "timestep_start": [10],
        "timestep_end": [15],
        "severity": [0.8],
    })
    validate_events(events)
    print("PASS: test_contracts_valid")


def test_contracts_reject_bad_data():
    from src.contracts import validate_events
    import pandera

    bad_events = pl.DataFrame({
        "scenario_id": ["sc_00000"],
        "object_id": ["sc_00000_ego"],
        "event_type": ["INVALID_TYPE"],
        "timestep_start": [10],
        "timestep_end": [15],
        "severity": [0.8],
    })
    try:
        validate_events(bad_events)
        assert False, "Should have raised SchemaError"
    except pandera.errors.SchemaError:
        pass
    print("PASS: test_contracts_reject_bad_data")


def test_detect_hard_brake():
    from src.detect import compute_speed_and_accel, detect_hard_brakes

    rows = []
    for t in range(20):
        speed = 20.0 if t < 10 else max(0, 20.0 - (t - 10) * 5.0)
        rows.append({
            "scenario_id": "test", "timestep": t, "timestamp_s": t * 0.1,
            "object_id": "test_ego", "object_type": "VEHICLE", "is_ego": True,
            "position_x": float(t), "position_y": 0.0, "heading": 0.0,
            "velocity_x": speed, "velocity_y": 0.0,
            "length_m": 4.5, "width_m": 2.0, "valid": True,
            "scenario_bucket": 0,
        })
    df = pl.DataFrame(rows)
    df = compute_speed_and_accel(df)
    events = detect_hard_brakes(df)
    assert len(events) > 0
    assert events["event_type"][0] == "HARD_BRAKE"
    print("PASS: test_detect_hard_brake")


def test_detect_no_false_positives():
    from src.detect import compute_speed_and_accel, detect_hard_brakes

    rows = []
    for t in range(20):
        rows.append({
            "scenario_id": "smooth", "timestep": t, "timestamp_s": t * 0.1,
            "object_id": "smooth_ego", "object_type": "VEHICLE", "is_ego": True,
            "position_x": float(t * 15 * 0.1), "position_y": 0.0, "heading": 0.0,
            "velocity_x": 15.0, "velocity_y": 0.0,
            "length_m": 4.5, "width_m": 2.0, "valid": True,
            "scenario_bucket": 0,
        })
    df = pl.DataFrame(rows)
    df = compute_speed_and_accel(df)
    events = detect_hard_brakes(df)
    assert len(events) == 0
    print("PASS: test_detect_no_false_positives")


def test_curate_dedup_reduces():
    from src.curate import cluster_and_dedup

    np.random.seed(42)
    n = 100
    features = pl.DataFrame({
        "scenario_id": [f"sc_{i:05d}" for i in range(n)],
        "mean_speed": np.random.uniform(10, 20, n).tolist(),
        "max_speed": np.random.uniform(15, 30, n).tolist(),
        "max_decel": np.random.uniform(-8, 0, n).tolist(),
        "trajectory_length": np.random.uniform(50, 200, n).tolist(),
        "n_agents": np.random.randint(2, 10, n).astype(np.int64).tolist(),
        "heading_variance": np.random.uniform(0, 0.5, n).tolist(),
        "has_event": [i % 3 == 0 for i in range(n)],
    })
    deduped = cluster_and_dedup(features)
    assert len(deduped) < len(features)
    assert len(deduped) > 0
    print("PASS: test_curate_dedup_reduces")


def test_full_pipeline_smoke():
    import shutil
    from src.generate import generate_scenarios, write_raw_parquet
    from src.ingest import run as ingest_run
    from src.detect import run as detect_run
    from src.featurize import run as featurize_run

    if TRACKS_DIR.exists():
        shutil.rmtree(TRACKS_DIR)
    if EVENTS_DIR.exists():
        shutil.rmtree(EVENTS_DIR)
    if FEATURES_PATH.exists():
        FEATURES_PATH.unlink()

    for f in RAW_DIR.glob("*.parquet"):
        f.unlink()

    df = generate_scenarios(n_scenarios=20, n_timesteps=30, n_agents=3, seed=77)
    write_raw_parquet(df)
    ingest_run()
    events = detect_run()
    features = featurize_run()

    assert TRACKS_DIR.exists()
    assert features.height == 20
    print("PASS: test_full_pipeline_smoke")


if __name__ == "__main__":
    test_generate()
    test_contracts_valid()
    test_contracts_reject_bad_data()
    test_detect_hard_brake()
    test_detect_no_false_positives()
    test_curate_dedup_reduces()
    test_full_pipeline_smoke()
    print("\n" + "=" * 40)
    print("ALL TESTS PASSED")
    print("=" * 40)
