import pandera.polars as pa
import polars as pl


class TrackSchema(pa.DataFrameModel):
    scenario_id: str
    timestep: int = pa.Field(ge=0)
    timestamp_s: float = pa.Field(ge=0.0)
    object_id: str
    object_type: str = pa.Field(isin=["VEHICLE", "PEDESTRIAN", "CYCLIST"])
    is_ego: bool
    position_x: float
    position_y: float
    heading: float = pa.Field(ge=-4.0, le=4.0)
    velocity_x: float
    velocity_y: float
    length_m: float = pa.Field(gt=0)
    width_m: float = pa.Field(gt=0)
    valid: bool


class EventSchema(pa.DataFrameModel):
    scenario_id: str
    object_id: str
    event_type: str = pa.Field(isin=["HARD_BRAKE", "CUT_IN", "NEAR_MISS"])
    timestep_start: int = pa.Field(ge=0)
    timestep_end: int = pa.Field(ge=0)
    severity: float = pa.Field(ge=0.0, le=1.0)


class FeatureSchema(pa.DataFrameModel):
    scenario_id: str
    mean_speed: float = pa.Field(ge=0.0)
    max_speed: float = pa.Field(ge=0.0)
    max_decel: float
    trajectory_length: float = pa.Field(ge=0.0)
    n_agents: int = pa.Field(ge=1)
    heading_variance: float = pa.Field(ge=0.0)
    has_event: bool


def validate_tracks(df: pl.DataFrame) -> pl.DataFrame:
    return TrackSchema.validate(df)


def validate_events(df: pl.DataFrame) -> pl.DataFrame:
    return EventSchema.validate(df)


def validate_features(df: pl.DataFrame) -> pl.DataFrame:
    return FeatureSchema.validate(df)
