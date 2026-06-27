import numpy as np
import polars as pl
from pathlib import Path
from src.config import RAW_DIR, SCENARIO_COUNT, TIMESTEPS, AGENTS_PER_SCENARIO


def _make_ego_trajectory(timesteps: int, dt: float = 0.1):
    speed = np.random.uniform(8, 25)
    heading = np.random.uniform(-np.pi, np.pi)
    vx = speed * np.cos(heading)
    vy = speed * np.sin(heading)

    x = np.cumsum(np.full(timesteps, vx * dt))
    y = np.cumsum(np.full(timesteps, vy * dt))
    velocity_x = np.full(timesteps, vx)
    velocity_y = np.full(timesteps, vy)

    return x, y, heading, velocity_x, velocity_y


def _inject_hard_brake(velocity_x, velocity_y, start: int, duration: int = 10):
    scale = np.linspace(1.0, 0.1, duration)
    end = min(start + duration, len(velocity_x))
    velocity_x[start:end] *= scale[: end - start]
    velocity_y[start:end] *= scale[: end - start]
    return velocity_x, velocity_y


def _inject_cut_in(x, y, ego_x, ego_y, merge_step: int):
    offset = np.random.choice([-3.5, 3.5])
    ramp = np.clip(np.linspace(1, 0, 20), 0, 1)
    for t in range(merge_step, min(merge_step + 20, len(x))):
        y[t] = ego_y[t] + offset * ramp[t - merge_step]
        x[t] = ego_x[t] + np.random.uniform(3, 6)
    return x, y


def generate_scenarios(
    n_scenarios: int = SCENARIO_COUNT,
    n_timesteps: int = TIMESTEPS,
    n_agents: int = AGENTS_PER_SCENARIO,
    seed: int = 42,
) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    np.random.seed(seed)

    rows = []

    for sc in range(n_scenarios):
        scenario_id = f"sc_{sc:05d}"
        timestamps = np.arange(n_timesteps) * 0.1

        ego_x, ego_y, ego_h, ego_vx, ego_vy = _make_ego_trajectory(n_timesteps)

        if rng.random() < 0.15 and n_timesteps > 30:
            brake_start = rng.integers(20, n_timesteps - 15)
            ego_vx, ego_vy = _inject_hard_brake(ego_vx.copy(), ego_vy.copy(), brake_start)
            ego_x = np.cumsum(ego_vx * 0.1)
            ego_y = np.cumsum(ego_vy * 0.1)

        for t in range(n_timesteps):
            rows.append({
                "scenario_id": scenario_id,
                "timestep": t,
                "timestamp_s": float(timestamps[t]),
                "object_id": f"{scenario_id}_ego",
                "object_type": "VEHICLE",
                "is_ego": True,
                "position_x": float(ego_x[t]),
                "position_y": float(ego_y[t]),
                "heading": float(ego_h),
                "velocity_x": float(ego_vx[t]),
                "velocity_y": float(ego_vy[t]),
                "length_m": 4.5,
                "width_m": 2.0,
                "valid": True,
            })

        for ag in range(n_agents):
            obj_id = f"{scenario_id}_agent_{ag:02d}"
            ag_x, ag_y, ag_h, ag_vx, ag_vy = _make_ego_trajectory(n_timesteps)

            ag_x += rng.uniform(-30, 30)
            ag_y += rng.uniform(-30, 30)

            if rng.random() < 0.10 and n_timesteps > 40:
                merge_step = rng.integers(10, n_timesteps - 25)
                ag_x, ag_y = _inject_cut_in(ag_x, ag_y, ego_x, ego_y, merge_step)

            obj_type = rng.choice(
                ["VEHICLE", "PEDESTRIAN", "CYCLIST"], p=[0.7, 0.2, 0.1]
            )
            length = {"VEHICLE": 4.5, "PEDESTRIAN": 0.5, "CYCLIST": 1.8}[obj_type]
            width = {"VEHICLE": 2.0, "PEDESTRIAN": 0.5, "CYCLIST": 0.7}[obj_type]

            for t in range(n_timesteps):
                rows.append({
                    "scenario_id": scenario_id,
                    "timestep": t,
                    "timestamp_s": float(timestamps[t]),
                    "object_id": obj_id,
                    "object_type": obj_type,
                    "is_ego": False,
                    "position_x": float(ag_x[t]),
                    "position_y": float(ag_y[t]),
                    "heading": float(ag_h),
                    "velocity_x": float(ag_vx[t]),
                    "velocity_y": float(ag_vy[t]),
                    "length_m": length,
                    "width_m": width,
                    "valid": True,
                })

    return pl.DataFrame(rows)


def write_raw_parquet(df: pl.DataFrame, out_dir: Path = RAW_DIR):
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "synthetic_shard_000.parquet"
    df.write_parquet(path)
    return path


if __name__ == "__main__":
    print(f"Generating {SCENARIO_COUNT} scenarios, {AGENTS_PER_SCENARIO} agents each, {TIMESTEPS} timesteps...")
    df = generate_scenarios()
    path = write_raw_parquet(df)
    print(f"Wrote {len(df):,} rows → {path}")
    print(f"Schema:\n{df.schema}")
