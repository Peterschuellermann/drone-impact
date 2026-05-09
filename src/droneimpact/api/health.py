from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    data_loaded: bool
    population_cells: int = 0
    building_cells: int = 0
    strikes_loaded: bool = False
    strike_count: int = 0


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    data_loaded = getattr(request.app.state, "data_loaded", False)
    pop_cells = getattr(request.app.state, "population_cells", 0)
    buildings = getattr(request.app.state, "buildings", None)
    building_cells = buildings.cell_count if buildings else 0
    strikes = getattr(request.app.state, "strikes", None)
    strikes_loaded = strikes is not None and strikes.count > 0
    strike_count = strikes.count if strikes is not None else 0
    return HealthResponse(
        status="ok" if data_loaded else "degraded",
        data_loaded=data_loaded,
        population_cells=pop_cells,
        building_cells=building_cells,
        strikes_loaded=strikes_loaded,
        strike_count=strike_count,
    )
