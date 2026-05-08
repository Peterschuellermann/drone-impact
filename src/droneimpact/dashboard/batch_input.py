from __future__ import annotations

import csv
import io

import streamlit as st

REQUIRED_COLUMNS = {"lat", "lon", "altitude_m", "heading_deg", "speed_m_s"}


def render_batch_input() -> list[dict] | None:
    mode = st.radio("Input mode", ["Manual", "CSV Upload"], horizontal=True)

    if mode == "Manual":
        return _render_manual_input()
    return _render_csv_input()


def _render_manual_input() -> list[dict] | None:
    n_drones = st.number_input("Number of drones", min_value=1, max_value=5, value=2)
    drones = []

    for i in range(n_drones):
        with st.expander(f"Drone {i + 1}", expanded=i == 0):
            drone_id = st.text_input("Drone ID", value=f"drone-{i + 1}", key=f"bid_{i}")
            lat = st.number_input("Latitude", value=48.5, min_value=-90.0, max_value=90.0,
                                  format="%.5f", key=f"blat_{i}")
            lon = st.number_input("Longitude", value=35.0 + i * 0.5, min_value=-180.0,
                                  max_value=180.0, format="%.5f", key=f"blon_{i}")
            alt = st.number_input("Altitude (m)", value=500.0, min_value=1.0, max_value=10000.0,
                                  key=f"balt_{i}")
            hdg = st.number_input("Heading (deg)", value=270.0, min_value=0.0, max_value=359.9,
                                  key=f"bhdg_{i}")
            spd = st.number_input("Speed (m/s)", value=51.4, min_value=20.0, max_value=300.0,
                                  key=f"bspd_{i}")
            drones.append({
                "drone_id": drone_id,
                "trajectory": {
                    "lat": lat, "lon": lon, "altitude_m": alt,
                    "heading_deg": hdg, "speed_m_s": spd,
                },
            })

    if st.button("Analyze Batch", type="primary", width="stretch"):
        return drones
    return None


def _render_csv_input() -> list[dict] | None:
    st.caption("CSV format: `drone_id,lat,lon,altitude_m,heading_deg,speed_m_s` — one row per drone")
    uploaded = st.file_uploader("Upload CSV", type=["csv"])

    if uploaded is None:
        return None

    drones, errors = parse_csv(uploaded.getvalue().decode("utf-8"))
    if errors:
        for e in errors:
            st.error(e)
        return None

    if not drones:
        st.error("CSV contains no valid rows.")
        return None

    if len(drones) > 100:
        st.error("Maximum 100 drones per batch.")
        return None

    st.success(f"Loaded {len(drones)} drones from CSV")
    st.dataframe([{
        "drone_id": d["drone_id"],
        "lat": d["trajectory"]["lat"],
        "lon": d["trajectory"]["lon"],
        "alt": d["trajectory"]["altitude_m"],
    } for d in drones])

    if st.button("Analyze Batch", type="primary", width="stretch"):
        return drones
    return None


def parse_csv(text: str) -> tuple[list[dict], list[str]]:
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return [], ["CSV has no header row."]

    fields = {f.strip().lower() for f in reader.fieldnames}
    missing = REQUIRED_COLUMNS - fields
    if missing:
        return [], [f"Missing required columns: {', '.join(sorted(missing))}"]

    drones = []
    errors = []
    for i, row in enumerate(reader, start=2):
        try:
            drone_id = row.get("drone_id", f"drone-{i - 1}") or f"drone-{i - 1}"
            drones.append({
                "drone_id": drone_id.strip(),
                "trajectory": {
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                    "altitude_m": float(row["altitude_m"]),
                    "heading_deg": float(row["heading_deg"]),
                    "speed_m_s": float(row["speed_m_s"]),
                },
            })
        except (ValueError, KeyError) as exc:
            errors.append(f"Row {i}: {exc}")

    return drones, errors
