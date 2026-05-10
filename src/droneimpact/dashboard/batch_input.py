from __future__ import annotations

import csv
import io

import streamlit as st

from droneimpact.dashboard.utils import load_multi_drone_scenarios

REQUIRED_COLUMNS = {"lat", "lon", "altitude_m", "heading_deg", "speed_m_s"}


def render_batch_input() -> list[dict] | None:
    mode = st.radio("Input mode", ["Scenario", "Manual", "CSV Upload"], horizontal=True)

    if mode == "Scenario":
        return _render_scenario_input()
    if mode == "Manual":
        return _render_manual_input()
    return _render_csv_input()


def _render_scenario_input() -> list[dict] | None:
    scenarios = load_multi_drone_scenarios()
    if not scenarios:
        st.warning("No multi-drone scenarios found in config.yaml.")
        return None

    scenario_names = [s["name"] for s in scenarios]
    scenario_map = {s["name"]: s for s in scenarios}

    selected_name = st.selectbox("Load scenario", scenario_names)
    scenario = scenario_map[selected_name]
    st.caption(scenario["description"])

    if "scenario_drones" not in st.session_state or st.session_state.get("scenario_name") != selected_name:
        st.session_state["scenario_drones"] = [
            {
                "drone_id": d["drone_id"],
                "lat": d["trajectory"]["lat"],
                "lon": d["trajectory"]["lon"],
                "altitude_m": d["trajectory"]["altitude_m"],
                "heading_deg": d["trajectory"]["heading_deg"],
                "speed_m_s": d["trajectory"]["speed_m_s"],
            }
            for d in scenario["drones"]
        ]
        st.session_state["scenario_name"] = selected_name

    drones_state = st.session_state["scenario_drones"]

    st.subheader(f"Drones ({len(drones_state)})")
    for i, d in enumerate(drones_state):
        with st.expander(f"{d['drone_id']}", expanded=False):
            d["drone_id"] = st.text_input("Drone ID", value=d["drone_id"], key=f"sc_id_{i}")
            d["lat"] = st.number_input("Latitude", value=d["lat"], min_value=-90.0,
                                       max_value=90.0, format="%.5f", key=f"sc_lat_{i}")
            d["lon"] = st.number_input("Longitude", value=d["lon"], min_value=-180.0,
                                       max_value=180.0, format="%.5f", key=f"sc_lon_{i}")
            d["altitude_m"] = st.number_input("Altitude (m)", value=d["altitude_m"], min_value=1.0,
                                              max_value=10000.0, key=f"sc_alt_{i}")
            d["heading_deg"] = st.number_input("Heading (deg)", value=d["heading_deg"], min_value=0.0,
                                               max_value=359.9, key=f"sc_hdg_{i}")
            d["speed_m_s"] = st.number_input("Speed (m/s)", value=d["speed_m_s"], min_value=20.0,
                                             max_value=300.0, key=f"sc_spd_{i}")

    if st.button("Analyze Batch", type="primary", width="stretch"):
        return [
            {
                "drone_id": d["drone_id"],
                "trajectory": {
                    "lat": d["lat"], "lon": d["lon"], "altitude_m": d["altitude_m"],
                    "heading_deg": d["heading_deg"], "speed_m_s": d["speed_m_s"],
                },
            }
            for d in drones_state
        ]
    return None


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

    reader.fieldnames = [f.strip().lower() for f in reader.fieldnames]
    missing = REQUIRED_COLUMNS - set(reader.fieldnames)
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
