from dataclasses import dataclass


@dataclass
class StateVector:
    lat: float
    lon: float
    altitude_m: float
    heading_deg: float
    speed_m_s: float


@dataclass
class TrajectoryPoint:
    index: int
    lat: float
    lon: float
    altitude_m: float
    distance_from_start_m: float
    heading_deg: float = 0.0
    speed_m_s: float = 0.0
