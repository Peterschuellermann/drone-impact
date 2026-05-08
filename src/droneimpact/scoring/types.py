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
    population_within_frag_radius: float = 0.0
    hit_branch_expected_casualties: float = 0.0
    high_risk: bool = False


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
class EngagementZone:
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


@dataclass
class RiskZone:
    start_index: int
    end_index: int
    start_distance_m: float
    end_distance_m: float
    peak_expected_casualties: float


@dataclass
class TrajectoryResult:
    trajectory_scores: list[PointScore]
    recommended_engagement: RecommendedEngagement
    impact_distributions: list[ImpactDistribution]
    metadata: dict = field(default_factory=dict)
    engagement_zones: list[EngagementZone] = field(default_factory=list)
    risk_zones: list[RiskZone] = field(default_factory=list)
    unconstrained_optimum: RecommendedEngagement | None = None
