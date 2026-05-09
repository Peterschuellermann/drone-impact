from __future__ import annotations

from dataclasses import dataclass

from droneimpact.config import AppConfig
from droneimpact.data.buildings import BuildingIndex
from droneimpact.data.dem import DEMIndex
from droneimpact.data.infrastructure import InfrastructureIndex
from droneimpact.data.population import PopulationIndex


@dataclass
class AppState:
    config: AppConfig
    dem: DEMIndex
    population: PopulationIndex
    infrastructure: InfrastructureIndex
    buildings: BuildingIndex
    data_loaded: bool
    population_cells: int
    strikes: object | None = None


def get_app_state(request) -> AppState:
    s = request.app.state
    buildings = getattr(s, "buildings", None)
    if buildings is None:
        buildings = BuildingIndex.empty(s.config.casualty.sheltering)
    return AppState(
        config=s.config,
        dem=s.dem,
        population=s.population,
        infrastructure=s.infrastructure,
        buildings=buildings,
        data_loaded=s.data_loaded,
        population_cells=s.population_cells,
        strikes=getattr(s, "strikes", None),
    )
