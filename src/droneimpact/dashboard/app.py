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
    parse_point_index_from_tooltip,
    prepare_animation_frames,
)
from droneimpact.dashboard.utils import (
    call_api,
    call_batch_api,
    call_point_impact_api,
    export_geojson,
    get_dashboard_config,
    load_scenarios,
)

st.set_page_config(page_title="DroneImpact", layout="wide")

page = st.sidebar.radio("Mode", ["Single Drone", "Batch Analysis"])


def _render_single_drone():
    st.title("DroneImpact — Single Drone Analysis")
    dash_cfg = get_dashboard_config()

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
            default_range_km = dash_cfg.default_max_range_m // 1000

        st.divider()
        st.header("Drone State")
        lat = st.number_input("Latitude", value=default_lat, min_value=-90.0, max_value=90.0, format="%.5f")
        lon = st.number_input("Longitude", value=default_lon, min_value=-180.0, max_value=180.0, format="%.5f")
        altitude_m = st.number_input("Altitude (m)", value=default_alt, min_value=1.0, max_value=10000.0)
        heading_deg = st.number_input("Heading (deg)", value=default_hdg, min_value=0.0, max_value=359.9)
        speed_m_s = st.number_input("Speed (m/s)", value=default_spd, min_value=20.0, max_value=300.0)

        st.divider()
        st.subheader("Analysis Parameters")
        evaluation_spacing_m = st.slider("Evaluation spacing (m)", 100, 5000, dash_cfg.default_evaluation_spacing_m, step=100)
        max_range_m = st.slider("Max range (km)", 1, 500, default_range_km) * 1000

        analyze_btn = st.button("Analyze", type="primary", width="stretch") or auto_submit

    @st.cache_data(ttl=dash_cfg.cache_ttl_sec, show_spinner=False)
    def _cached_api_call(lat, lon, altitude_m, heading_deg, speed_m_s, spacing, range_m):
        return call_api(
            {"lat": lat, "lon": lon, "altitude_m": altitude_m,
             "heading_deg": heading_deg, "speed_m_s": speed_m_s},
            evaluation_spacing_m=spacing,
            max_range_m=range_m,
        )

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

        @st.fragment
        def _map_fragment():
            scores = result["trajectory_scores"]
            rec_idx = result["recommended_engagement"]["point_index"]

            if "selected_point_idx" not in st.session_state:
                st.session_state["selected_point_idx"] = rec_idx

            selected_idx = st.session_state["selected_point_idx"]

            score_by_idx = {pt["point_index"]: pt for pt in scores}
            selected_pt = score_by_idx.get(selected_idx)

            traj_map = make_trajectory_map(result, selected_point_idx=selected_idx)
            add_risk_zone_overlay(
                traj_map,
                scores,
                result.get("risk_zones", []),
            )

            _ranked_marker_colors = {
                2: ("#f97316", "white"),
                3: ("#eab308", "black"),
                4: ("#3b82f6", "white"),
                5: ("#a855f7", "white"),
            }
            for re in result.get("ranked_engagements", [])[1:]:
                rank = re["rank"]
                color, text_color = _ranked_marker_colors.get(rank, ("#6b7280", "white"))
                icon_html = (
                    f'<div style="'
                    f'background-color:{color};color:{text_color};'
                    f'border-radius:50%;width:26px;height:26px;'
                    f'display:flex;align-items:center;justify-content:center;'
                    f'font-weight:bold;font-size:14px;border:2px solid white;'
                    f'box-shadow:0 1px 3px rgba(0,0,0,0.4);">'
                    f'{rank}</div>'
                )
                popup_html = (
                    f"<b>Rank {rank} interception point</b><br>"
                    f"Expected casualties: {re['expected_casualties']:.4f}<br>"
                    f"{re['reasoning']}"
                )
                folium.Marker(
                    location=[re["lat"], re["lon"]],
                    icon=folium.DivIcon(
                        html=icon_html,
                        icon_size=(26, 26),
                        icon_anchor=(13, 13),
                    ),
                    popup=folium.Popup(popup_html, max_width=300),
                    tooltip=f"Rank {rank} fallback interception point",
                ).add_to(traj_map)

            impact_data = None
            if selected_pt:
                try:
                    impact_data = call_point_impact_api({
                        "lat": selected_pt["lat"],
                        "lon": selected_pt["lon"],
                        "altitude_m": selected_pt["altitude_m"],
                        "heading_deg": selected_pt.get("heading_deg", heading_deg),
                        "speed_m_s": selected_pt.get("speed_m_s", speed_m_s),
                    })
                    add_fallout_overlay(traj_map, impact_data)
                except Exception as e:
                    st.warning(f"Could not load point impact data: {e}")

            if "focused_point_idx" not in st.session_state:
                st.session_state["focused_point_idx"] = selected_idx
            force_center = selected_idx != st.session_state["focused_point_idx"]
            if force_center:
                st.session_state["focused_point_idx"] = selected_idx
            map_center = [selected_pt["lat"], selected_pt["lon"]] if (force_center and selected_pt) else None
            map_zoom = 11 if force_center else None

            st.caption("Click an evaluation point to inspect its fallout area.")
            traj_data = st_folium(
                traj_map,
                center=map_center,
                zoom=map_zoom,
                use_container_width=True,
                height=600,
                returned_objects=["last_object_clicked_tooltip"],
                layer_control=folium.LayerControl(),
                key="trajectory_map",
            )

            clicked_tooltip = (traj_data or {}).get("last_object_clicked_tooltip")
            clicked_idx = parse_point_index_from_tooltip(clicked_tooltip)
            if clicked_idx is not None and clicked_idx != selected_idx:
                st.session_state["selected_point_idx"] = clicked_idx
                st.rerun(scope="fragment")

            if selected_pt and impact_data:
                st.markdown(make_point_detail_panel(selected_pt, impact_data))

        with tab_map:
            _map_fragment()

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
                st_folium(coloured_map, use_container_width=True, height=450, returned_objects=[], layer_control=folium.LayerControl())

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

    st_folium(make_batch_map(batch_result), use_container_width=True, height=500, returned_objects=[], layer_control=folium.LayerControl())

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

        @st.fragment
        def _batch_map_fragment():
            scores = drone_result["trajectory_scores"]
            rec_idx = drone_result["recommended_engagement"]["point_index"]

            batch_sel_key = f"batch_selected_point_{idx}"
            if batch_sel_key not in st.session_state:
                st.session_state[batch_sel_key] = rec_idx

            selected_idx = st.session_state[batch_sel_key]

            score_by_idx = {pt["point_index"]: pt for pt in scores}
            selected_pt = score_by_idx.get(selected_idx)

            traj_map = make_trajectory_map(drone_result, selected_point_idx=selected_idx)
            add_risk_zone_overlay(
                traj_map,
                scores,
                drone_result.get("risk_zones", []),
            )

            impact_data = None
            if selected_pt:
                pt_heading = selected_pt.get("heading_deg", 0.0)
                pt_speed = selected_pt.get("speed_m_s", 51.4)
                try:
                    impact_data = call_point_impact_api({
                        "lat": selected_pt["lat"],
                        "lon": selected_pt["lon"],
                        "altitude_m": selected_pt["altitude_m"],
                        "heading_deg": pt_heading,
                        "speed_m_s": pt_speed,
                    })
                    add_fallout_overlay(traj_map, impact_data)
                except Exception as e:
                    st.warning(f"Could not load point impact data: {e}")

            batch_focused_key = f"batch_focused_point_{idx}"
            if batch_focused_key not in st.session_state:
                st.session_state[batch_focused_key] = selected_idx
            force_center = selected_idx != st.session_state[batch_focused_key]
            if force_center:
                st.session_state[batch_focused_key] = selected_idx
            map_center = [selected_pt["lat"], selected_pt["lon"]] if (force_center and selected_pt) else None
            map_zoom = 11 if force_center else None

            st.caption("Click an evaluation point to inspect its fallout area.")
            traj_data = st_folium(
                traj_map,
                center=map_center,
                zoom=map_zoom,
                use_container_width=True,
                height=500,
                returned_objects=["last_object_clicked_tooltip"],
                layer_control=folium.LayerControl(),
                key=f"batch_traj_map_{idx}",
            )

            clicked_tooltip = (traj_data or {}).get("last_object_clicked_tooltip")
            clicked_idx = parse_point_index_from_tooltip(clicked_tooltip)
            if clicked_idx is not None and clicked_idx != selected_idx:
                st.session_state[batch_sel_key] = clicked_idx
                st.rerun(scope="fragment")

            if selected_pt and impact_data:
                st.markdown(make_point_detail_panel(selected_pt, impact_data))

        with tab_map:
            _batch_map_fragment()

        with tab_impact:
            st.plotly_chart(make_impact_scatter(drone_result), width="stretch")

        with tab_risk:
            st.plotly_chart(make_risk_profile(drone_result), width="stretch")

        with tab_stats:
            st.markdown(make_stats_panel(drone_result))

        st.divider()
        st.download_button(
            label=f"Export {selected} as GeoJSON",
            data=export_geojson(drone_result),
            file_name=f"droneimpact_{selected}.geojson",
            mime="application/geo+json",
            key=f"batch_export_{idx}",
        )

        st.divider()
        st.subheader("Trajectory Replay")
        first_pt = drone_result["trajectory_scores"][0] if drone_result["trajectory_scores"] else {}
        replay_speed = first_pt.get("speed_m_s", 51.4)
        frames = prepare_animation_frames(drone_result, replay_speed)

        if frames:
            n_frames = len(frames)
            step = st.slider("Evaluation point", 0, n_frames - 1, 0, key=f"batch_replay_{idx}")
            frame = frames[step]

            col_map, col_stats = st.columns([2, 1])

            with col_map:
                coloured_map = make_coloured_trajectory(drone_result)
                folium.CircleMarker(
                    [frame["lat"], frame["lon"]],
                    radius=10, color=frame["colour"], fill=True,
                    fill_opacity=1.0, weight=3,
                ).add_to(coloured_map)
                st_folium(coloured_map, use_container_width=True, height=450, returned_objects=[],
                          layer_control=folium.LayerControl(), key=f"batch_replay_map_{idx}")

            with col_stats:
                if frame["is_recommended"]:
                    st.success("RECOMMENDED ENGAGEMENT POINT")
                st.metric("Position", f"{frame['lat']:.5f}, {frame['lon']:.5f}")
                st.metric("Altitude", f"{frame['altitude_m']:.0f} m")
                st.metric("Distance", f"{frame['distance_from_current_m'] / 1000:.1f} km")
                st.metric("Expected Casualties", f"{frame['expected_casualties']:.4f}")
                st.metric("Engagement Score", f"{frame['engagement_score']:.4f}")
                st.caption(f"Point {step + 1} / {n_frames}")

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
