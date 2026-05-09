#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DATA_DIR="$PROJECT_DIR/data"
TEMP_DIR="$DATA_DIR/.tmp"

mkdir -p "$DATA_DIR" "$TEMP_DIR"

echo "=== DroneImpact Data Download ==="
echo "Target directory: $DATA_DIR"
echo ""

# ---------------------------------------------------------------------------
# 1. Kontur Population Dataset (Ukraine)
# ---------------------------------------------------------------------------
KONTUR_FILE="$DATA_DIR/kontur_ukraine.gpkg"
if [ -f "$KONTUR_FILE" ]; then
    echo "[1/4] Kontur population: already exists, skipping"
else
    echo "[1/4] Downloading Kontur population dataset (Ukraine)..."
    curl -fSL --progress-bar \
        "https://geodata-eu-central-1-kontur-public.s3.amazonaws.com/kontur_datasets/kontur_population_UA_20231101.gpkg.gz" \
        -o "$TEMP_DIR/kontur_ukraine.gpkg.gz"
    echo "      Decompressing..."
    gunzip -c "$TEMP_DIR/kontur_ukraine.gpkg.gz" > "$KONTUR_FILE"
    rm "$TEMP_DIR/kontur_ukraine.gpkg.gz"
    echo "      Done: $(du -h "$KONTUR_FILE" | cut -f1)"
fi
echo ""

# ---------------------------------------------------------------------------
# 2. Copernicus GLO-30 DEM
# ---------------------------------------------------------------------------
DEM_FILE="$DATA_DIR/ukraine_dem.tif"
if [ -f "$DEM_FILE" ]; then
    echo "[2/4] DEM: already exists, skipping"
else
    echo "[2/4] Downloading Copernicus GLO-30 DEM tiles for Ukraine..."
    DEM_TILE_DIR="$TEMP_DIR/dem_tiles"
    mkdir -p "$DEM_TILE_DIR"

    # Ukraine bounding box: ~44°N–53°N, 22°E–40°E
    DOWNLOADED=0
    SKIPPED=0
    for lat in $(seq 44 52); do
        for lon in $(seq 22 40); do
            latstr=$(printf "N%02d_00" "$lat")
            lonstr=$(printf "E%03d_00" "$lon")
            tile="Copernicus_DSM_COG_10_${latstr}_${lonstr}_DEM"
            outfile="$DEM_TILE_DIR/${tile}.tif"

            if [ -f "$outfile" ]; then
                DOWNLOADED=$((DOWNLOADED + 1))
                continue
            fi

            url="https://copernicus-dem-30m.s3.amazonaws.com/${tile}/${tile}.tif"
            if curl -sfL "$url" -o "$outfile" 2>/dev/null; then
                DOWNLOADED=$((DOWNLOADED + 1))
                printf "\r      Downloaded %d tiles..." "$DOWNLOADED"
            else
                SKIPPED=$((SKIPPED + 1))
            fi
        done
    done
    echo ""
    echo "      Downloaded $DOWNLOADED tiles, skipped $SKIPPED (sea/no data)"

    echo "      Merging tiles into single GeoTIFF..."
    python3 "$SCRIPT_DIR/merge_dem.py" "$DEM_TILE_DIR" "$DEM_FILE"
    echo "      Done: $(du -h "$DEM_FILE" | cut -f1)"
    echo "      Cleaning up tiles..."
    rm -rf "$DEM_TILE_DIR"
fi
echo ""

# ---------------------------------------------------------------------------
# 3. OpenStreetMap Ukraine — infrastructure extract
# ---------------------------------------------------------------------------
INFRA_FILE="$DATA_DIR/ukraine_infra.geojson"
if [ -f "$INFRA_FILE" ]; then
    echo "[3/4] OSM infrastructure: already exists, skipping"
else
    echo "[3/4] Downloading OpenStreetMap Ukraine extract..."
    OSM_PBF="$TEMP_DIR/ukraine-latest.osm.pbf"

    if [ ! -f "$OSM_PBF" ]; then
        curl -fSL --progress-bar \
            "https://download.geofabrik.de/europe/ukraine-latest.osm.pbf" \
            -o "$OSM_PBF"
        echo "      Downloaded: $(du -h "$OSM_PBF" | cut -f1)"
    fi

    echo "      Extracting infrastructure features..."
    python3 "$SCRIPT_DIR/extract_infra.py" "$OSM_PBF" "$INFRA_FILE"
    echo "      Done: $(du -h "$INFRA_FILE" | cut -f1)"
    echo "      Cleaning up PBF..."
    rm "$OSM_PBF"
fi
echo ""

# ---------------------------------------------------------------------------
# 4. Ukraine Strike Locations (Bellingcat)
# ---------------------------------------------------------------------------
STRIKES_FILE="$DATA_DIR/ukraine_strikes.geojson"
if [ -f "$STRIKES_FILE" ]; then
    echo "[4/4] Strike locations: already exists, skipping"
else
    echo "[4/4] Ingesting strike locations from Bellingcat..."
    python "$SCRIPT_DIR/ingest_strikes.py" --output "$STRIKES_FILE"
    echo "      Done: $(wc -l < "$STRIKES_FILE") lines"
fi
echo ""

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
rmdir "$TEMP_DIR" 2>/dev/null || true

echo "=== All data files ready ==="
echo ""
ls -lh "$DATA_DIR"/*.gpkg "$DATA_DIR"/*.tif "$DATA_DIR"/*.geojson 2>/dev/null
