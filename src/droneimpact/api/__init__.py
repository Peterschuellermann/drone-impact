from __future__ import annotations

from dataclasses import dataclass

from droneimpact.config import AppConfig
from droneimpact.data.dem import DEMIndex
from droneimpact.data.infrastructure import InfrastructureIndex
from droneimpact.data.population import PopulationIndex


@dataclass
class AppState:
    config: AppConfig
    dem: DEMIndex
    population: PopulationIndex
    infrastructure: InfrastructureIndex
    data_loaded: bool
    population_cells: int


def get_app_state(request) -> AppState:
    s = request.app.state
    return AppState(
        config=s.config,
        dem=s.dem,
        population=s.population,
        infrastructure=s.infrastructure,
        data_loaded=s.data_loaded,
        population_cells=s.population_cells,
    )
