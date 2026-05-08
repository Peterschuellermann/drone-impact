from __future__ import annotations

import streamlit as st
from streamlit_folium import st_folium

from droneimpact.dashboard.batch_input import render_batch_input
from droneimpact.dashboard.components import (
    make_batch_map,
    make_impact_scatter,
    make_priority_table,
    make_risk_profile,
    make_stats_panel,
    make_trajectory_map,
)
from droneimpact.dashboard.utils import call_api, call_batch_api, export_geojson

st.set_page_config(page_title="DroneImpact", layout="wide")

page = st.sidebar.radio("Mode", ["Single Drone", "Batch Analysis"])


def _render_single_drone():
    st.title("DroneImpact — Single Drone Analysis")

    with st.sidebar:
        st.header("Drone State")
        lat = st.number_input("Latitude", value=48.5, min_value=-90.0, max_value=90.0, format="%.5f")
        lon = st.number_input("Longitude", value=35.0, min_value=-180.0, max_value=180.0, format="%.5f")
        altitude_m = st.number_input("Altitude (m)", value=500.0, min_value=1.0, max_value=10000.0)
        heading_deg = st.number_input("Heading (deg)", value=270.0, min_value=0.0, max_value=359.9)
        speed_m_s = st.number_input("Speed (m/s)", value=51.4, min_value=20.0, max_value=300.0)

        st.divider()
        st.subheader("Analysis Parameters")
        evaluation_spacing_m = st.slider("Evaluation spacing (m)", 100, 5000, 500, step=100)
        max_range_m = st.slider("Max range (km)", 1, 500, 250) * 1000

        analyze_btn = st.button("Analyze", type="primary", use_container_width=True)

    @st.cache_data(ttl=300, show_spinner=False)
    def _cached_api_call(lat, lon, altitude_m, heading_deg, speed_m_s, _spacing, _range):
        return call_api({
            "lat": lat, "lon": lon, "altitude_m": altitude_m,
            "heading_deg": heading_deg, "speed_m_s": speed_m_s,
        })

    if analyze_btn:
        with st.spinner("Running analysis..."):
            try:
                result = _cached_api_call(
                    lat, lon, altitude_m, heading_deg, speed_m_s,
                    evaluation_spacing_m, max_range_m,
                )
                st.session_state["result"] = result
            except Exception as e:
                st.error(f"API error: {e}")
                st.stop()

    if "result" in st.session_state:
        result = st.session_state["result"]

        tab_map, tab_impact, tab_risk, tab_stats = st.tabs([
            "Trajectory Map", "Impact Distribution", "Risk Profile", "Statistics",
        ])

        with tab_map:
            st_folium(make_trajectory_map(result), use_container_width=True, height=600)

        with tab_impact:
            st.plotly_chart(make_impact_scatter(result), use_container_width=True)

        with tab_risk:
            st.plotly_chart(make_risk_profile(result), use_container_width=True)

        with tab_stats:
            st.markdown(make_stats_panel(result))

        st.divider()
        st.download_button(
            label="Export as GeoJSON",
            data=export_geojson(result),
            file_name="droneimpact_result.geojson",
            mime="application/geo+json",
        )
    else:
        st.info("Configure drone parameters in the sidebar and click **Analyze** to begin.")


def _render_batch():
    st.title("DroneImpact — Batch Analysis")

    with st.sidebar:
        drones = render_batch_input()

    if drones is not None:
        with st.spinner(f"Analysing {len(drones)} drones..."):
            try:
                batch_result = call_batch_api(drones)
                st.session_state["batch_result"] = batch_result
            except Exception as e:
                st.error(f"Batch API error: {e}")
                st.stop()

    if "batch_result" not in st.session_state:
        st.info("Configure drones in the sidebar and click **Analyze Batch**.")
        return

    batch_result = st.session_state["batch_result"]

    errors = batch_result.get("errors", [])
    if errors:
        st.warning(f"{len(errors)} drone(s) failed:")
        for err in errors:
            st.caption(f"- {err.get('drone_id', '?')}: {err.get('error', 'unknown')}")

    results = batch_result.get("results", [])
    if not results:
        st.error("All drones failed. Check the API and retry.")
        return

    st_folium(make_batch_map(batch_result), use_container_width=True, height=500)

    st.subheader("Priority Ranking")
    rows = make_priority_table(batch_result)
    st.dataframe(rows, use_container_width=True, hide_index=True)

    st.subheader("Drill-Down")
    drone_ids = [r.get("drone_id") or f"Drone {i + 1}" for i, r in enumerate(results)]
    selected = st.selectbox("Select drone for detail view", drone_ids)

    if selected:
        idx = drone_ids.index(selected)
        drone_result = results[idx]

        tab_map, tab_impact, tab_risk, tab_stats = st.tabs([
            "Trajectory Map", "Impact Distribution", "Risk Profile", "Statistics",
        ])

        with tab_map:
            st_folium(make_trajectory_map(drone_result), use_container_width=True, height=500)

        with tab_impact:
            st.plotly_chart(make_impact_scatter(drone_result), use_container_width=True)

        with tab_risk:
            st.plotly_chart(make_risk_profile(drone_result), use_container_width=True)

        with tab_stats:
            st.markdown(make_stats_panel(drone_result))

    st.subheader("Compare")
    compare_ids = st.multiselect("Select 2-3 drones to compare", drone_ids, max_selections=3)
    if len(compare_ids) >= 2:
        cols = st.columns(len(compare_ids))
        for col, cid in zip(cols, compare_ids):
            cidx = drone_ids.index(cid)
            with col:
                st.markdown(f"**{cid}**")
                st.markdown(make_stats_panel(results[cidx]))


if page == "Single Drone":
    _render_single_drone()
else:
    _render_batch()
