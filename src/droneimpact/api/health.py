from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    data_loaded: bool
    population_cells: int = 0


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    data_loaded = getattr(request.app.state, "data_loaded", False)
    pop_cells = getattr(request.app.state, "population_cells", 0)
    return HealthResponse(
        status="ok" if data_loaded else "degraded",
        data_loaded=data_loaded,
        population_cells=pop_cells,
    )
