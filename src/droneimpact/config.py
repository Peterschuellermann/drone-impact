from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, model_validator


class Shahed136Params(BaseModel):
    mass_kg: float
    warhead_mass_kg: float
    cruise_speed_m_s: float
    glide_ratio: float
    drag_coeff_tumbling: float
    reference_area_m2: float
    fragment_reference_area_m2: float = 0.5
    fragment_mass_mean_kg: float = 50.0
    fragment_mass_std_kg: float = 10.0


class PhysicsConfig(BaseModel):
    n_monte_carlo_samples: int
    evaluation_spacing_m: int
    shahed136: Shahed136Params
    m1_sigma_heading_deg: float
    m1_sigma_glide_ratio: float
    m2_sigma_init_deg: float
    m2_sigma_turn_deg_per_s: float
    m2_dt_s: float
    m2_max_time_s: float
    m2_descent_rate_m_s: float
    m2_power_duration_min_s: float = 1.0
    m2_power_duration_max_s: float = 10.0
    m3_heading_spread_deg: float = 60.0
    m3_sigma_speed_m_s: float
    m3_speed_reduction_factor: float = 0.7
    m3_sigma_cd: float
    m3_dt_s: float
    m3_max_steps: int
    m3_pitch_range_deg: float = 20.0
    atmosphere_scale_height_m: float = 8500.0


class ModeWeights(BaseModel):
    propulsion_loss: float
    loss_of_control: float
    break_apart: float

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> "ModeWeights":
        total = self.propulsion_loss + self.loss_of_control + self.break_apart
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"mode_weights must sum to 1.0, got {total}")
        return self


class EngagementConfig(BaseModel):
    p_kill: float
    mode_weights: ModeWeights


class BlastParams(BaseModel):
    tnt_equivalent_kg: float
    lethal_radius_m: float
    injury_radius_m: float
    p_lethal: float
    p_injury: float


class FragParams(BaseModel):
    lethal_radius_m: float
    danger_radius_m: float
    p_frag_lethal: float
    p_frag_danger: float


class InfraWeights(BaseModel):
    power_plant: float
    hospital: float
    water_works: float
    bridge: float
    school: float


class InfraConfig(BaseModel):
    penalty_radius_m: float
    max_penalty: float
    weights: InfraWeights


class CasualtyBand(BaseModel):
    radius_m: float
    probability: float


class CasualtyConfig(BaseModel):
    blast: BlastParams
    fragmentation: FragParams
    infrastructure: InfraConfig
    blast_bands: list[CasualtyBand] | None = None
    frag_bands: list[CasualtyBand] | None = None


class DataPaths(BaseModel):
    population_path: str
    dem_path: str
    infrastructure_path: str


class ScoringConfig(BaseModel):
    population_empty_threshold: float = 0.0
    population_high_risk_threshold: float = 50.0
    dense_spacing_m: float = 50.0
    miss_cache_agl_round_m: float = 10.0
    miss_cache_heading_round_deg: float = 1.0
    zone_caution_threshold: float = 0.1
    zone_nogo_threshold: float = 1.0


class AppConfig(BaseModel):
    version: str
    physics: PhysicsConfig
    engagement: EngagementConfig
    casualty: CasualtyConfig
    data: DataPaths
    scoring: ScoringConfig = ScoringConfig()


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    with open(path) as f:
        raw = yaml.safe_load(f)
    return AppConfig.model_validate(raw)
