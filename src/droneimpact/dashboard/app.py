from __future__ import annotations

import folium
import streamlit as st
from streamlit_folium import st_folium

from droneimpact.dashboard.batch_input import render_batch_input
from droneimpact.dashboard.components import (
    add_fallout_overlay,
    add_interception_zones_layer,
    add_risk_zone_overlay,
    make_batch_map,
    make_coloured_trajectory,
    make_drone_overview_map,
    make_impact_scatter,
    make_multi_trajectory_map,
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
    call_predict_targets,
    call_strikes_api,
    compute_bearing,
    export_geojson,
    get_dashboard_config,
    load_multi_drone_scenarios,
    load_scenarios,
)

st.set_page_config(page_title="DroneImpact", layout="wide")

page = st.sidebar.radio("Mode", ["Single Drone", "Batch Analysis", "Multi-Trajectory"])


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

            point_indices = [pt["point_index"] for pt in scores]
            point_labels = {
                pt["point_index"]: (
                    f"Point {pt['point_index']} — "
                    f"{pt['distance_from_current_m']:.0f} m — "
                    f"Casualties: {pt['expected_casualties']:.3f}"
                    + (" [RECOMMENDED]" if pt["point_index"] == rec_idx else "")
                )
                for pt in scores
            }
            selected_idx = st.selectbox(
                "Select evaluation point",
                options=point_indices,
                index=point_indices.index(st.session_state["selected_point_idx"])
                if st.session_state["selected_point_idx"] in point_indices else 0,
                format_func=lambda i: point_labels[i],
                key="point_selector",
            )
            st.session_state["selected_point_idx"] = selected_idx

            score_by_idx = {pt["point_index"]: pt for pt in scores}
            selected_pt = score_by_idx.get(selected_idx)

            traj_map = make_trajectory_map(result, selected_point_idx=selected_idx)
            add_risk_zone_overlay(
                traj_map,
                scores,
                result.get("risk_zones", []),
            )
            add_interception_zones_layer(
                traj_map,
                result.get("interception_zones", []),
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

            map_center = None
            map_zoom = None
            if selected_pt:
                map_center = [selected_pt["lat"], selected_pt["lon"]]
                map_zoom = 11

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

            point_indices = [pt["point_index"] for pt in scores]
            point_labels = {
                pt["point_index"]: (
                    f"Point {pt['point_index']} — "
                    f"{pt['distance_from_current_m']:.0f} m — "
                    f"Casualties: {pt['expected_casualties']:.3f}"
                    + (" [RECOMMENDED]" if pt["point_index"] == rec_idx else "")
                )
                for pt in scores
            }
            selected_idx = st.selectbox(
                "Select evaluation point",
                options=point_indices,
                index=point_indices.index(st.session_state[batch_sel_key])
                if st.session_state[batch_sel_key] in point_indices else 0,
                format_func=lambda i: point_labels[i],
                key=f"batch_point_selector_{idx}",
            )
            st.session_state[batch_sel_key] = selected_idx

            score_by_idx = {pt["point_index"]: pt for pt in scores}
            selected_pt = score_by_idx.get(selected_idx)

            traj_map = make_trajectory_map(drone_result, selected_point_idx=selected_idx)
            add_risk_zone_overlay(
                traj_map,
                scores,
                drone_result.get("risk_zones", []),
            )
            add_interception_zones_layer(
                traj_map,
                drone_result.get("interception_zones", []),
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

            map_center = None
            map_zoom = None
            if selected_pt:
                map_center = [selected_pt["lat"], selected_pt["lon"]]
                map_zoom = 11

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


def _render_multi_trajectory():
    st.title("DroneImpact — Multi-Trajectory Prediction")

    multi_scenarios = load_multi_drone_scenarios()

    with st.sidebar:
        input_mode = st.radio("Input", ["Single drone", "Scenario"], horizontal=True, key="mt_input_mode")

        if input_mode == "Scenario" and multi_scenarios:
            scenario_names = [s["name"] for s in multi_scenarios]
            scenario_map = {s["name"]: s for s in multi_scenarios}
            selected_name = st.selectbox("Load scenario", scenario_names, key="mt_scenario_sel")
            scenario = scenario_map[selected_name]
            st.caption(scenario["description"])
        else:
            if input_mode == "Scenario" and not multi_scenarios:
                st.warning("No multi-drone scenarios in config.")
                input_mode = "Single drone"

        if input_mode == "Single drone":
            st.header("Drone State")
            lat = st.number_input("Latitude", value=52.0, format="%.5f", min_value=-90.0, max_value=90.0)
            lon = st.number_input("Longitude", value=33.5, format="%.5f", min_value=-180.0, max_value=180.0)
            altitude_m = st.number_input("Altitude (m)", value=400.0, min_value=1.0, max_value=10000.0)
            heading_deg = st.number_input("Heading (deg)", value=230.0, min_value=0.0, max_value=359.9)
            speed_m_s = st.number_input("Speed (m/s)", value=51.4, min_value=20.0, max_value=300.0)

        st.divider()
        st.subheader("Prediction Parameters")
        max_range_m = st.slider("Max range (km)", 50, 500, 250) * 1000
        max_targets = st.slider("Max candidate targets", 5, 30, 15)

        predict_btn = st.button("Predict Targets", type="primary", width="stretch")

    if input_mode == "Scenario":
        _render_multi_trajectory_scenario(
            scenario, max_range_m, max_targets, predict_btn,
        )
    else:
        _render_multi_trajectory_single(
            lat, lon, heading_deg, speed_m_s, altitude_m,
            max_range_m, max_targets, predict_btn,
        )


def _render_multi_trajectory_single(
    lat, lon, heading_deg, speed_m_s, altitude_m,
    max_range_m, max_targets, predict_btn,
):
    if predict_btn:
        with st.spinner("Predicting target trajectories..."):
            prediction = call_predict_targets(
                lat, lon, heading_deg, speed_m_s, altitude_m,
                max_range_m=max_range_m, max_targets=max_targets,
            )
        if prediction is None:
            st.error("Target prediction unavailable. Check that strike data is loaded.")
            st.stop()
        if not prediction["candidates"]:
            st.warning("No reachable targets found. Try increasing range or checking strike data.")
            st.stop()
        st.session_state["mt_prediction"] = prediction
        st.session_state["mt_scored_idx"] = 0
        st.session_state["mt_scored_result"] = None

    if "mt_prediction" not in st.session_state:
        st.info("Enter drone state in the sidebar and click **Predict Targets** to begin.")
        return

    prediction = st.session_state["mt_prediction"]
    candidates = prediction["candidates"]
    meta = prediction["metadata"]
    scored_idx = st.session_state.get("mt_scored_idx", 0)
    scored_result = st.session_state.get("mt_scored_result")

    if scored_result is None:
        most_probable = candidates[0]
        target = most_probable["target"]
        with st.spinner("Scoring most probable trajectory..."):
            try:
                target_heading = compute_bearing(lat, lon, target["lat"], target["lon"])
                scored_result = call_api(
                    {"lat": lat, "lon": lon, "altitude_m": altitude_m,
                     "heading_deg": target_heading, "speed_m_s": speed_m_s},
                    max_range_m=int(most_probable["distance_m"] * 1.1),
                )
                st.session_state["mt_scored_result"] = scored_result
            except Exception as e:
                st.warning(f"Could not score trajectory: {e}")

    col1, col2, col3 = st.columns(3)
    col1.metric("Targets considered", meta["targets_considered"])
    col2.metric("Reachable targets", meta["targets_reachable"])
    col3.metric("Prediction time", f"{meta['prediction_time_ms']:.0f} ms")

    traj_map = make_multi_trajectory_map(
        lat, lon, candidates,
        scored_result=scored_result,
        scored_candidate_idx=scored_idx,
    )
    st.caption("Click a trajectory or target in the layer panel to explore. Most probable trajectory is scored.")
    st_folium(traj_map, width="stretch", height=600, returned_objects=[], key="mt_map")

    st.subheader("Candidate Targets")
    table_data = []
    for i, c in enumerate(candidates):
        table_data.append({
            "Rank": i + 1,
            "Target": c["target"]["name"],
            "Category": c["target"]["category"],
            "Probability": f"{c['probability']:.1%}",
            "Distance (km)": f"{c['distance_m']/1000:.0f}",
            "Heading Δ": f"{c['heading_delta_deg']:.0f}°",
            "Historical Strikes": c["target"]["historical_strikes"],
        })
    st.dataframe(table_data, use_container_width=True, hide_index=True)

    st.subheader("Score a specific trajectory")
    selected_rank = st.selectbox(
        "Select trajectory to score",
        options=list(range(1, len(candidates) + 1)),
        format_func=lambda i: f"#{i}: {candidates[i-1]['target']['name']} ({candidates[i-1]['probability']:.1%})",
        index=scored_idx,
    )
    selected_idx_new = selected_rank - 1
    score_btn = st.button("Score selected trajectory")
    if score_btn or selected_idx_new != scored_idx:
        st.session_state["mt_scored_idx"] = selected_idx_new
        selected_c = candidates[selected_idx_new]
        target = selected_c["target"]
        target_heading = compute_bearing(lat, lon, target["lat"], target["lon"])
        with st.spinner(f"Scoring trajectory to {target['name']}..."):
            try:
                new_result = call_api(
                    {"lat": lat, "lon": lon, "altitude_m": altitude_m,
                     "heading_deg": target_heading, "speed_m_s": speed_m_s},
                    max_range_m=int(selected_c["distance_m"] * 1.1),
                )
                st.session_state["mt_scored_result"] = new_result
                st.rerun()
            except Exception as e:
                st.warning(f"Could not score: {e}")


def _find_converging_threats(predictions: dict) -> dict[str, list[str]]:
    target_to_drones: dict[str, list[str]] = {}
    for drone_id, pred in predictions.items():
        if not pred or not pred.get("candidates"):
            continue
        top = pred["candidates"][0]
        target_name = top["target"]["name"]
        target_to_drones.setdefault(target_name, []).append(drone_id)
    return {t: ds for t, ds in target_to_drones.items() if len(ds) > 1}


def _render_multi_trajectory_scenario(
    scenario, max_range_m, max_targets, predict_btn,
):
    drones = scenario["drones"]

    if predict_btn:
        predictions = {}
        progress = st.progress(0, text="Predicting targets for all drones...")
        for i, d in enumerate(drones):
            traj = d["trajectory"]
            pred = call_predict_targets(
                traj["lat"], traj["lon"], traj["heading_deg"],
                traj["speed_m_s"], traj["altitude_m"],
                max_range_m=max_range_m, max_targets=max_targets,
            )
            predictions[d["drone_id"]] = pred
            progress.progress((i + 1) / len(drones), text=f"Predicted {i + 1}/{len(drones)} drones")
        progress.empty()
        st.session_state["mt_scenario_predictions"] = predictions
        st.session_state["mt_scenario_name"] = scenario["name"]

    if "mt_scenario_predictions" not in st.session_state:
        overview_drones = [{"drone_id": d["drone_id"], "trajectory": d["trajectory"]} for d in drones]
        st_folium(
            make_drone_overview_map(overview_drones),
            width="stretch", height=400, returned_objects=[], key="mt_overview",
        )
        st.info("Click **Predict Targets** to analyze all drones in this scenario.")
        return

    predictions = st.session_state["mt_scenario_predictions"]
    converging = _find_converging_threats(predictions)

    if converging:
        st.warning(
            f"**Converging threats detected:** "
            + ", ".join(
                f"{target} ({', '.join(ds)})"
                for target, ds in converging.items()
            )
        )

    converging_drones = set()
    for ds in converging.values():
        converging_drones.update(ds)

    st.subheader("Tactical Summary")
    summary_rows = []
    for d in drones:
        drone_id = d["drone_id"]
        pred = predictions.get(drone_id)
        if not pred or not pred.get("candidates"):
            summary_rows.append({
                "Drone": drone_id,
                "Top Target": "—",
                "Probability": "—",
                "Distance (km)": "—",
                "Converging": "",
            })
            continue
        top = pred["candidates"][0]
        target_name = top["target"]["name"]
        is_converging = drone_id in converging_drones
        summary_rows.append({
            "Drone": drone_id,
            "Top Target": target_name,
            "Probability": f"{top['probability']:.1%}",
            "Distance (km)": f"{top['distance_m']/1000:.0f}",
            "Converging": "CONVERGING" if is_converging else "",
        })
    st.dataframe(summary_rows, use_container_width=True, hide_index=True)

    st.subheader("Drone Detail")
    drone_ids = [d["drone_id"] for d in drones]
    selected_drone = st.selectbox("Select drone for trajectory view", drone_ids, key="mt_drone_sel")
    selected_drone_data = next(d for d in drones if d["drone_id"] == selected_drone)
    traj = selected_drone_data["trajectory"]
    pred = predictions.get(selected_drone)

    if not pred or not pred.get("candidates"):
        st.warning(f"No predictions available for {selected_drone}.")
        return

    candidates = pred["candidates"]
    meta = pred["metadata"]

    col1, col2, col3 = st.columns(3)
    col1.metric("Targets considered", meta["targets_considered"])
    col2.metric("Reachable targets", meta["targets_reachable"])
    col3.metric("Prediction time", f"{meta['prediction_time_ms']:.0f} ms")

    traj_map = make_multi_trajectory_map(
        traj["lat"], traj["lon"], candidates,
    )
    st_folium(traj_map, width="stretch", height=500, returned_objects=[], key="mt_detail_map")

    table_data = []
    for i, c in enumerate(candidates):
        table_data.append({
            "Rank": i + 1,
            "Target": c["target"]["name"],
            "Probability": f"{c['probability']:.1%}",
            "Distance (km)": f"{c['distance_m']/1000:.0f}",
            "Heading Δ": f"{c['heading_delta_deg']:.0f}°",
            "Historical Strikes": c["target"]["historical_strikes"],
        })
    st.dataframe(table_data, use_container_width=True, hide_index=True)


if page == "Single Drone":
    _render_single_drone()
elif page == "Batch Analysis":
    _render_batch()
else:
    _render_multi_trajectory()
