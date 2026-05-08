from __future__ import annotations

import streamlit as st
from streamlit_folium import st_folium

from droneimpact.dashboard.components import (
    make_impact_scatter,
    make_risk_profile,
    make_stats_panel,
    make_trajectory_map,
)
from droneimpact.dashboard.utils import call_api, export_geojson

st.set_page_config(page_title="DroneImpact", layout="wide")
st.title("DroneImpact Analysis Dashboard")

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
def _cached_api_call(
    lat: float, lon: float, altitude_m: float,
    heading_deg: float, speed_m_s: float,
    evaluation_spacing_m: int, max_range_m: int,
) -> dict:
    return call_api({
        "lat": lat,
        "lon": lon,
        "altitude_m": altitude_m,
        "heading_deg": heading_deg,
        "speed_m_s": speed_m_s,
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
        traj_map = make_trajectory_map(result)
        st_folium(traj_map, use_container_width=True, height=600)

    with tab_impact:
        fig = make_impact_scatter(result)
        st.plotly_chart(fig, use_container_width=True)

    with tab_risk:
        fig = make_risk_profile(result)
        st.plotly_chart(fig, use_container_width=True)

    with tab_stats:
        st.markdown(make_stats_panel(result))

    st.divider()
    geojson_str = export_geojson(result)
    st.download_button(
        label="Export as GeoJSON",
        data=geojson_str,
        file_name="droneimpact_result.geojson",
        mime="application/geo+json",
    )
else:
    st.info("Configure drone parameters in the sidebar and click **Analyze** to begin.")
