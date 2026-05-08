"""Merge Copernicus GLO-30 DEM tiles into a single GeoTIFF using rasterio."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.merge import merge
from rasterio.transform import from_bounds


def main(tile_dir: str, output_path: str) -> None:
    tiles = sorted(Path(tile_dir).glob("*.tif"))
    if not tiles:
        print(f"No .tif files found in {tile_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"  Merging {len(tiles)} tiles...")
    datasets = [rasterio.open(t) for t in tiles]
    mosaic, transform = merge(datasets)

    profile = datasets[0].profile.copy()
    profile.update(
        driver="GTiff",
        height=mosaic.shape[1],
        width=mosaic.shape[2],
        transform=transform,
        BIGTIFF="YES",
        compress="deflate",
        predictor=2,
        tiled=True,
        blockxsize=512,
        blockysize=512,
    )

    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(mosaic)

    for ds in datasets:
        ds.close()

    print(f"  Written to {output_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <tile_dir> <output.tif>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
