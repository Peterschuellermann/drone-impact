import h3


def make_test_population(
    centre_lat: float = 48.0,
    centre_lon: float = 31.0,
    pop_density: float = 5000.0,
    radius_cells: int = 2,
    resolution: int = 8,
) -> dict[str, float]:
    """Creates a synthetic population cluster (pop_density = pop/km²) around a centre point."""
    centre = h3.latlng_to_cell(centre_lat, centre_lon, resolution)
    cells = h3.grid_disk(centre, radius_cells)
    return {cell: pop_density for cell in cells}
