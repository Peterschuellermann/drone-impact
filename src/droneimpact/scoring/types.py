from dataclasses import dataclass, field


@dataclass
class ModeScore:
    weight: float
    expected_casualties: float
    cep_m: float


@dataclass
class PointScore:
    point_index: int
    lat: float
    lon: float
    altitude_m: float
    distance_from_start_m: float
    expected_casualties: float
    engagement_score: float
    breakdown: dict[str, ModeScore]
    miss_branch_expected_casualties: float


@dataclass
class ImpactEllipse:
    centre_lat: float
    centre_lon: float
    semi_major_m: float
    semi_minor_m: float
    orientation_deg: float


@dataclass
class ImpactDistribution:
    point_index: int
    mode: str
    impact_ellipse: ImpactEllipse


@dataclass
class RecommendedEngagement:
    point_index: int
    lat: float
    lon: float
    altitude_m: float
    distance_from_current_m: float
    expected_casualties: float
    engagement_score: float
    reasoning: str


@dataclass
class TrajectoryResult:
    trajectory_scores: list[PointScore]
    recommended_engagement: RecommendedEngagement
    impact_distributions: list[ImpactDistribution]
    metadata: dict = field(default_factory=dict)
