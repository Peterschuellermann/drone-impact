from __future__ import annotations

from pydantic import BaseModel, Field


class TrajectoryInput(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    altitude_m: float = Field(gt=0, le=10_000)
    heading_deg: float = Field(ge=0, lt=360)
    speed_m_s: float = Field(ge=20, le=300)


class SingleDroneRequest(BaseModel):
    drone_id: str | None = None
    trajectory: TrajectoryInput
    max_range_m: int = Field(default=250_000, ge=1_000, le=1_000_000)
    evaluation_spacing_m: int = Field(default=500, ge=100, le=5_000)
    include_heatmap: bool = False


class ModeBreakdown(BaseModel):
    weight: float
    expected_casualties: float
    cep_m: float


class TrajectoryPointScore(BaseModel):
    point_index: int
    lat: float
    lon: float
    altitude_m: float
    distance_from_current_m: float
    expected_casualties: float
    engagement_score: float
    breakdown: dict[str, ModeBreakdown]
    miss_branch_expected_casualties: float


class ImpactEllipseSchema(BaseModel):
    centre_lat: float
    centre_lon: float
    semi_major_m: float
    semi_minor_m: float
    orientation_deg: float


class ImpactDistributionSchema(BaseModel):
    point_index: int
    mode: str
    impact_ellipse: ImpactEllipseSchema


class RecommendedEngagementSchema(BaseModel):
    point_index: int
    lat: float
    lon: float
    altitude_m: float
    distance_from_current_m: float
    expected_casualties: float
    engagement_score: float
    reasoning: str


class EngagementZoneSchema(BaseModel):
    classification: str
    start_index: int
    end_index: int
    start_distance_m: float
    end_distance_m: float
    start_lat: float
    start_lon: float
    end_lat: float
    end_lon: float
    peak_expected_casualties: float
    mean_expected_casualties: float
    population_in_zone: float
    reasons: list[str]


class MetadataSchema(BaseModel):
    n_trajectory_points: int
    n_monte_carlo_samples: int
    simulation_time_ms: float
    population_dataset: str
    infrastructure_dataset: str
    n_points_skipped: int | None = None
    n_points_dense: int | None = None


class SingleDroneResponse(BaseModel):
    drone_id: str | None
    computed_at_utc: str
    recommended_engagement: RecommendedEngagementSchema
    trajectory_scores: list[TrajectoryPointScore]
    impact_distributions: list[ImpactDistributionSchema]
    metadata: MetadataSchema
    engagement_zones: list[EngagementZoneSchema] | None = None
