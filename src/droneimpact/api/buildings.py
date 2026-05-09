from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

import h3

router = APIRouter()


class BuildingCell(BaseModel):
    h3_id: str
    protection_class: str
    boundary: list[list[float]]


class BuildingCoverageResponse(BaseModel):
    cells: list[BuildingCell]
    total_cells: int


@router.get("/buildings/coverage", response_model=BuildingCoverageResponse)
async def building_coverage(
    request: Request,
    lat: float | None = None,
    lon: float | None = None,
    radius_km: float = 50.0,
) -> BuildingCoverageResponse:
    buildings = getattr(request.app.state, "buildings", None)
    if buildings is None or buildings.cell_count == 0:
        return BuildingCoverageResponse(cells=[], total_cells=0)

    cell_class = buildings._cell_class

    if lat is not None and lon is not None:
        centre = h3.latlng_to_cell(lat, lon, buildings._resolution)
        edge_m = h3.average_hexagon_edge_length(buildings._resolution, unit="m")
        k = max(1, int(radius_km * 1000 / (edge_m * 1.732)))
        visible = set(h3.grid_disk(centre, k))
        filtered = {c: cls for c, cls in cell_class.items() if c in visible}
    else:
        filtered = cell_class

    cells = []
    for h3_id, cls_name in filtered.items():
        boundary = h3.cell_to_boundary(h3_id)
        cells.append(BuildingCell(
            h3_id=h3_id,
            protection_class=cls_name,
            boundary=[[lat, lon] for lat, lon in boundary],
        ))

    return BuildingCoverageResponse(cells=cells, total_cells=buildings.cell_count)
