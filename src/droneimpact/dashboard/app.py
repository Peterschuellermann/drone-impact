from __future__ import annotations

import folium
import streamlit as st
from streamlit_folium import st_folium

from droneimpact.dashboard.batch_input import render_batch_input
from droneimpact.dashboard.components import (
    add_fallout_overlay,
    add_risk_zone_overlay,
    make_batch_map,
    make_coloured_trajectory,
    make_impact_scatter,
    make_point_detail_panel,
    make_priority_table,
    make_risk_profile,
    make_stats_panel,
    make_trajectory_map,
    prepare_animation_frames,
)
from droneimpact.dashboard.utils import (
    call_api,
    call_batch_api,
    call_point_impact_api,
    export_geojson,
    load_scenarios,
)

st.set_page_config(page_title="DroneImpact", layout="wide")

page = st.sidebar.radio("Mode", ["Single Drone", "Batch Analysis"])


def _render_single_drone():
    st.title("DroneImpact — Single Drone Analysis")

    scenarios = load_scenarios()
    scenario_names = [s["name"] for s in scenarios] + ["Custom"]
    scenario_map = {s["name"]: s for s in scenarios}

    with st.sidebar:
        st.header("Demo Scenarios")
        selected_scenario = st.selectbox(
            "Select Scenario",
            scenario_names,
            index=len(scenario_names) - 1,
            key="scenario_select",
        )

        is_scenario = selected_scenario != "Custom"
        auto_submit = False

        if is_scenario:
            sc = scenario_map[selected_scenario]
            st.caption(sc["description"])
            traj = sc["trajectory"]
            default_lat = traj["lat"]
            default_lon = traj["lon"]
            default_alt = traj["altitude_m"]
            default_hdg = traj["heading_deg"]
            default_spd = traj["speed_m_s"]
            default_range_km = sc["max_range_m"] // 1000
            auto_submit = True
        else:
            default_lat = 48.5
            default_lon = 35.0
            default_alt = 500.0
            default_hdg = 270.0
            default_spd = 51.4
            default_range_km = 250

        st.divider()
        st.header("Drone State")
        lat = st.number_input("Latitude", value=default_lat, min_value=-90.0, max_value=90.0, format="%.5f")
        lon = st.number_input("Longitude", value=default_lon, min_value=-180.0, max_value=180.0, format="%.5f")
        altitude_m = st.number_input("Altitude (m)", value=default_alt, min_value=1.0, max_value=10000.0)
        heading_deg = st.number_input("Heading (deg)", value=default_hdg, min_value=0.0, max_value=359.9)
        speed_m_s = st.number_input("Speed (m/s)", value=default_spd, min_value=20.0, max_value=300.0)

        st.divider()
        st.subheader("Analysis Parameters")
        evaluation_spacing_m = st.slider("Evaluation spacing (m)", 100, 5000, 500, step=100)
        max_range_m = st.slider("Max range (km)", 1, 500, default_range_km) * 1000

        analyze_btn = st.button("Analyze", type="primary", width="stretch") or auto_submit

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
            traj_map = make_trajectory_map(result)
            add_risk_zone_overlay(
                traj_map,
                result["trajectory_scores"],
                result.get("risk_zones", []),
            )
            st_folium(traj_map, width="stretch", height=600, returned_objects=[])

            # --- Interactive point inspection ---
            scores = result["trajectory_scores"]
            rec_idx = result["recommended_engagement"]["point_index"]

            point_options = []
            default_select = 0
            for i, pt in enumerate(scores):
                dist_km = pt["distance_from_current_m"] / 1000
                label = f"Point #{pt['point_index']} -- {dist_km:.1f} km"
                if pt["point_index"] == rec_idx:
                    label += " (recommended)"
                    default_select = i
                point_options.append(label)

            if point_options:
                selected_pt_idx = st.selectbox(
                    "Inspect evaluation point",
                    range(len(point_options)),
                    index=default_select,
                    format_func=lambda i: point_options[i],
                    key="inspect_point",
                )

                selected_pt = scores[selected_pt_idx]
                try:
                    impact_data = call_point_impact_api({
                        "lat": selected_pt["lat"],
                        "lon": selected_pt["lon"],
                        "altitude_m": selected_pt["altitude_m"],
                        "heading_deg": heading_deg,
                        "speed_m_s": speed_m_s,
                    })

                    fallout_map = make_coloured_trajectory(result)
                    add_risk_zone_overlay(
                        fallout_map,
                        result["trajectory_scores"],
                        result.get("risk_zones", []),
                    )
                    folium.CircleMarker(
                        [selected_pt["lat"], selected_pt["lon"]],
                        radius=10, color="#8b5cf6", fill=True,
                        fill_opacity=1.0, weight=3,
                        tooltip="Selected point",
                    ).add_to(fallout_map)
                    add_fallout_overlay(fallout_map, impact_data)
                    st_folium(fallout_map, width="stretch", height=450, returned_objects=[])

                    st.markdown(make_point_detail_panel(selected_pt, impact_data))
                except Exception as e:
                    st.warning(f"Could not load point impact data: {e}")

        with tab_impact:
            st.plotly_chart(make_impact_scatter(result), width="stretch")

        with tab_risk:
            st.plotly_chart(make_risk_profile(result), width="stretch")

        with tab_stats:
            st.markdown(make_stats_panel(result))

        st.divider()
        st.download_button(
            label="Export as GeoJSON",
            data=export_geojson(result),
            file_name="droneimpact_result.geojson",
            mime="application/geo+json",
        )

        st.divider()
        st.subheader("Trajectory Replay")

        frames = prepare_animation_frames(result, speed_m_s)

        if frames:
            n_frames = len(frames)
            step = st.slider("Evaluation point", 0, n_frames - 1, 0, key="replay_step")
            frame = frames[step]

            col_map, col_stats = st.columns([2, 1])

            with col_map:
                coloured_map = make_coloured_trajectory(result)
                folium.CircleMarker(
                    [frame["lat"], frame["lon"]],
                    radius=10, color=frame["colour"], fill=True,
                    fill_opacity=1.0, weight=3,
                ).add_to(coloured_map)
                st_folium(coloured_map, width="stretch", height=450, returned_objects=[])

            with col_stats:
                is_rec = frame["is_recommended"]
                if is_rec:
                    st.success("RECOMMENDED ENGAGEMENT POINT")
                st.metric("Position", f"{frame['lat']:.5f}, {frame['lon']:.5f}")
                st.metric("Altitude", f"{frame['altitude_m']:.0f} m")
                st.metric("Distance", f"{frame['distance_from_current_m'] / 1000:.1f} km")
                st.metric("Expected Casualties", f"{frame['expected_casualties']:.4f}")
                st.metric("Engagement Score", f"{frame['engagement_score']:.4f}")
                st.caption(f"Point {step + 1} / {n_frames}")
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

    st_folium(make_batch_map(batch_result), width="stretch", height=500, returned_objects=[])

    st.subheader("Priority Ranking")
    rows = make_priority_table(batch_result)
    st.dataframe(rows, width="stretch", hide_index=True)

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
            st_folium(make_trajectory_map(drone_result), width="stretch", height=500, returned_objects=[])

        with tab_impact:
            st.plotly_chart(make_impact_scatter(drone_result), width="stretch")

        with tab_risk:
            st.plotly_chart(make_risk_profile(drone_result), width="stretch")

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
