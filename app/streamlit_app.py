from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import pydeck as pdk
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from unisa_air_twin.arpac import clean_air_quality
from unisa_air_twin.config import load_settings
from unisa_air_twin.gis import (
    available_timestamps,
    build_interpolation_grid,
    sensor_snapshot,
    value_color,
)
from unisa_air_twin.model import estimate_campus_air_quality
from unisa_air_twin.scenario import apply_scenario
from unisa_air_twin.sensors import create_virtual_sensors
from unisa_air_twin.storage import geojson_points_to_frame, read_geojson, read_table
from unisa_air_twin.utils import read_json

st.set_page_config(page_title="UNISA Air Quality Digital Twin - MVP", layout="wide")

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.3rem; padding-bottom: 2rem;}
    div[data-testid="stMetric"] {
        border-left: 3px solid #2a915f;
        padding-left: 0.85rem;
        background: rgba(42, 145, 95, 0.055);
    }
    .small-note {color: #5c625f; font-size: 0.88rem; line-height: 1.35;}
    .status-line {
        padding: 0.65rem 0;
        border-top: 1px solid rgba(49, 51, 63, 0.12);
        border-bottom: 1px solid rgba(49, 51, 63, 0.12);
        color: #39413d;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict, dict[str, dict]]:
    settings = load_settings()
    sensors = geojson_points_to_frame(settings.processed_dir / "campus_virtual_sensors.geojson")
    if sensors.empty:
        sensors = create_virtual_sensors(settings)
    estimates = read_table(settings.processed_dir / "campus_air_quality_estimates.parquet")
    if estimates.empty:
        clean_air_quality(settings)
        estimates = estimate_campus_air_quality(settings)
    estimates["timestamp"] = pd.to_datetime(estimates["timestamp"], errors="coerce")
    stations = read_table(settings.processed_dir / "arpac_station_metadata.parquet")
    schema_report = read_json(settings.processed_dir / "schema_report.json", default={"warnings": []})
    layers = {
        "buildings": read_geojson(settings.processed_dir / "campus_buildings.geojson"),
        "roads": read_geojson(settings.processed_dir / "campus_roads.geojson"),
        "green": read_geojson(settings.processed_dir / "campus_green.geojson"),
        "transport": read_geojson(settings.processed_dir / "campus_transport.geojson"),
        "parking": read_geojson(settings.processed_dir / "campus_parking.geojson"),
    }
    return estimates, sensors, stations, schema_report if isinstance(schema_report, dict) else {"warnings": []}, layers


def color_series(values: pd.Series, palette: str = "value") -> list[list[int]]:
    if values.empty:
        return []
    low = float(values.min())
    high = float(values.max())
    return [value_color(float(value), low, high, palette=palette) for value in values]


def build_base_layers(osm_layers: dict[str, dict], toggles: dict[str, bool]) -> list[pdk.Layer]:
    layers: list[pdk.Layer] = []
    if toggles.get("buildings"):
        layers.append(
            pdk.Layer(
                "GeoJsonLayer",
                osm_layers["buildings"],
                stroked=True,
                filled=True,
                get_fill_color=[88, 96, 105, 55],
                get_line_color=[65, 72, 80, 130],
                line_width_min_pixels=1,
                pickable=False,
            )
        )
    if toggles.get("green"):
        layers.append(
            pdk.Layer(
                "GeoJsonLayer",
                osm_layers["green"],
                stroked=False,
                filled=True,
                get_fill_color=[69, 145, 86, 95],
                pickable=False,
            )
        )
    if toggles.get("roads"):
        layers.append(
            pdk.Layer(
                "GeoJsonLayer",
                osm_layers["roads"],
                stroked=True,
                filled=False,
                get_line_color=[82, 86, 91, 150],
                line_width_min_pixels=2,
                pickable=False,
            )
        )
    if toggles.get("transport"):
        layers.append(
            pdk.Layer(
                "GeoJsonLayer",
                osm_layers["transport"],
                stroked=True,
                filled=True,
                get_fill_color=[40, 110, 190, 145],
                get_line_color=[20, 65, 120, 200],
                point_radius_min_pixels=5,
                pickable=True,
            )
        )
    if toggles.get("parking"):
        layers.append(
            pdk.Layer(
                "GeoJsonLayer",
                osm_layers["parking"],
                stroked=True,
                filled=True,
                get_fill_color=[145, 115, 60, 120],
                get_line_color=[95, 72, 36, 200],
                point_radius_min_pixels=5,
                pickable=True,
            )
        )
    return layers


def sensor_layer(snapshot: pd.DataFrame, value_column: str, palette: str = "value") -> pdk.Layer:
    sensors = snapshot.copy()
    sensors["color"] = color_series(sensors[value_column], palette=palette)
    return pdk.Layer(
        "ScatterplotLayer",
        sensors,
        get_position="[lon, lat]",
        get_radius=72,
        get_fill_color="color",
        get_line_color=[255, 255, 255, 220],
        line_width_min_pixels=1,
        pickable=True,
    )


def grid_layer(grid: pd.DataFrame, value_column: str) -> pdk.Layer:
    return pdk.Layer(
        "PolygonLayer",
        grid,
        get_polygon="polygon",
        get_fill_color="color",
        get_line_color=[255, 255, 255, 18],
        line_width_min_pixels=0.15,
        pickable=True,
        opacity=0.78,
    )


def station_layer(stations: pd.DataFrame) -> pdk.Layer | None:
    station_points = stations.dropna(subset=["lat", "lon"]) if not stations.empty else pd.DataFrame()
    if station_points.empty:
        return None
    return pdk.Layer(
        "ScatterplotLayer",
        station_points,
        get_position="[lon, lat]",
        get_radius=115,
        get_fill_color=[35, 70, 165, 95],
        get_line_color=[255, 255, 255, 180],
        line_width_min_pixels=1,
        pickable=True,
    )


def deck(layers: list[pdk.Layer], tooltip: dict) -> pdk.Deck:
    return pdk.Deck(
        map_style="light",
        initial_view_state=pdk.ViewState(
            latitude=float(settings.campus["fallback_latitude"]),
            longitude=float(settings.campus["fallback_longitude"]),
            zoom=14.2,
            pitch=0,
        ),
        layers=layers,
        tooltip=tooltip,
    )


settings = load_settings()
estimates, sensors, stations, schema_report, osm_layers = load_data()
pollutants = sorted(estimates["pollutant"].dropna().unique()) if not estimates.empty else ["pm10"]

with st.sidebar:
    st.header("Controlli GIS")
    selected_pollutant = st.selectbox("Inquinante", pollutants, index=0)
    timestamps = available_timestamps(estimates, selected_pollutant)
    timestamp_labels = [pd.Timestamp(ts).strftime("%Y-%m-%d %H:%M") for ts in timestamps]
    selected_label = st.select_slider(
        "Ora simulata",
        options=timestamp_labels,
        value=timestamp_labels[-1] if timestamp_labels else None,
    )
    selected_timestamp = pd.Timestamp(selected_label) if selected_label else pd.Timestamp.now().floor("h")
    grid_resolution = st.slider("Risoluzione griglia", 14, 34, 24, step=2)
    st.divider()
    layer_toggles = {
        "heatmap": st.checkbox("Heatmap interpolata", value=True),
        "sensors": st.checkbox("Sensori virtuali", value=True),
        "stations": st.checkbox("Stazioni ARPAC", value=True),
        "buildings": st.checkbox("Edifici", value=True),
        "roads": st.checkbox("Strade", value=True),
        "green": st.checkbox("Aree verdi", value=True),
        "transport": st.checkbox("Trasporto pubblico", value=True),
        "parking": st.checkbox("Parcheggi", value=True),
    }

snapshot = sensor_snapshot(estimates, selected_pollutant, selected_timestamp)
zones = ["all", *sorted(snapshot["zone"].dropna().unique())] if not snapshot.empty else ["all"]

st.title("UNISA Air Quality Digital Twin - MVP")
st.markdown(
    f"""
    <div class="status-line">
    Inquinante <b>{selected_pollutant.upper()}</b> · ora <b>{selected_timestamp:%Y-%m-%d %H:%M}</b> ·
    {len(snapshot)} sensori virtuali attivi · modello dimostrativo, non ufficiale.
    </div>
    """,
    unsafe_allow_html=True,
)

tab_gis, tab_scenario, tab_timeseries, tab_quality = st.tabs(
    ["GIS operativo", "Simulazione what-if", "Serie temporali", "Qualita dati"]
)

with tab_gis:
    left, right = st.columns([3, 1])
    with right:
        if not snapshot.empty:
            st.metric("Media sensori", f"{snapshot['estimated_value'].mean():.1f}")
            st.metric("Massimo", f"{snapshot['estimated_value'].max():.1f}")
            st.metric("Minimo", f"{snapshot['estimated_value'].min():.1f}")
        st.markdown(
            "<p class='small-note'>La superficie continua e ottenuta con interpolazione IDW sui sensori virtuali del campus.</p>",
            unsafe_allow_html=True,
        )
    with left:
        if snapshot.empty:
            st.warning("Nessun dato disponibile per l'ora selezionata.")
        else:
            map_layers = build_base_layers(osm_layers, layer_toggles)
            grid = build_interpolation_grid(snapshot, resolution=grid_resolution)
            if layer_toggles["heatmap"] and not grid.empty:
                map_layers.append(grid_layer(grid, "estimated_value"))
            if layer_toggles["sensors"]:
                map_layers.append(sensor_layer(snapshot, "estimated_value"))
            if layer_toggles["stations"]:
                arpac_layer = station_layer(stations)
                if arpac_layer is not None:
                    map_layers.append(arpac_layer)
            st.pydeck_chart(
                deck(
                    map_layers,
                    {
                        "html": "<b>{sensor_name}</b><br/>Valore: {estimated_value}<br/>Zona: {zone}",
                        "style": {"backgroundColor": "white", "color": "black"},
                    },
                ),
                width="stretch",
            )
            st.dataframe(
                snapshot[
                    [
                        "sensor_name",
                        "zone",
                        "estimated_value",
                        "traffic_index",
                        "green_index",
                        "wind_speed_10m",
                        "precipitation",
                    ]
                ].sort_values("estimated_value", ascending=False),
                width="stretch",
                hide_index=True,
            )

with tab_scenario:
    preset = st.selectbox(
        "Preset scenario",
        [
            "Personalizzato",
            "Traffico ridotto al terminal bus",
            "Giornata di pioggia",
            "Vento forte",
            "Campus green mobility",
        ],
    )
    preset_values = {
        "Personalizzato": (0.2, 1.0, False, "all", 0.0),
        "Traffico ridotto al terminal bus": (0.4, 1.0, False, "mobilita", 0.0),
        "Giornata di pioggia": (0.1, 1.0, True, "all", 0.0),
        "Vento forte": (0.0, 1.8, False, "all", 0.0),
        "Campus green mobility": (0.35, 1.1, False, "all", 0.25),
    }
    default_traffic, default_wind, default_rain, default_zone, default_green = preset_values[preset]
    control_a, control_b, control_c, control_d = st.columns(4)
    traffic_reduction = control_a.slider("Riduzione traffico", 0, 50, int(default_traffic * 100), step=5) / 100
    wind_multiplier = control_b.slider("Moltiplicatore vento", 0.5, 2.0, float(default_wind), step=0.1)
    focus_zone = control_c.selectbox(
        "Zona intervento",
        zones,
        index=zones.index(default_zone) if default_zone in zones else 0,
    )
    green_improvement = control_d.slider("Verde aggiunto", 0, 50, int(default_green * 100), step=5) / 100
    rain_event = st.toggle("Evento di pioggia", value=default_rain)

    scenario_snapshot = apply_scenario(
        snapshot,
        settings,
        traffic_reduction=traffic_reduction,
        wind_multiplier=wind_multiplier,
        rain_event=rain_event,
        focus_zone=focus_zone,
        green_improvement=green_improvement,
    )
    if scenario_snapshot.empty:
        st.warning("Scenario non disponibile per l'ora selezionata.")
    else:
        scenario_grid = build_interpolation_grid(
            scenario_snapshot,
            value_column="scenario_value",
            resolution=grid_resolution,
        )
        delta_grid = build_interpolation_grid(
            scenario_snapshot.rename(columns={"delta": "delta_value"}),
            value_column="delta_value",
            resolution=grid_resolution,
        )
        scenario_snapshot["delta_color"] = color_series(scenario_snapshot["delta"], palette="delta")
        metric_a, metric_b, metric_c = st.columns(3)
        metric_a.metric("Delta medio", f"{scenario_snapshot['delta'].mean():+.2f}")
        metric_b.metric("Miglioramento massimo", f"{scenario_snapshot['delta'].min():+.2f}")
        metric_c.metric("Sensori migliorati", f"{int((scenario_snapshot['delta'] < 0).sum())}/{len(scenario_snapshot)}")

        map_a, map_b = st.columns(2)
        with map_a:
            st.subheader("Scenario")
            scenario_layers = build_base_layers(osm_layers, layer_toggles)
            if layer_toggles["heatmap"] and not scenario_grid.empty:
                scenario_layers.append(grid_layer(scenario_grid, "scenario_value"))
            if layer_toggles["sensors"]:
                scenario_layers.append(sensor_layer(scenario_snapshot, "scenario_value"))
            st.pydeck_chart(
                deck(
                    scenario_layers,
                    {
                        "html": "<b>{sensor_name}</b><br/>Scenario: {scenario_value}<br/>Baseline: {estimated_value}",
                        "style": {"backgroundColor": "white", "color": "black"},
                    },
                ),
                width="stretch",
            )
        with map_b:
            st.subheader("Delta")
            delta_layers = build_base_layers(osm_layers, layer_toggles)
            if layer_toggles["heatmap"] and not delta_grid.empty:
                delta_layers.append(grid_layer(delta_grid, "delta_value"))
            if layer_toggles["sensors"]:
                delta_layers.append(
                    pdk.Layer(
                        "ScatterplotLayer",
                        scenario_snapshot,
                        get_position="[lon, lat]",
                        get_radius=72,
                        get_fill_color="delta_color",
                        get_line_color=[255, 255, 255, 220],
                        line_width_min_pixels=1,
                        pickable=True,
                    )
                )
            st.pydeck_chart(
                deck(
                    delta_layers,
                    {
                        "html": "<b>{sensor_name}</b><br/>Delta: {delta}<br/>Scenario: {scenario_value}",
                        "style": {"backgroundColor": "white", "color": "black"},
                    },
                ),
                width="stretch",
            )

        fig = px.bar(
            scenario_snapshot.sort_values("delta"),
            x="sensor_name",
            y="delta",
            color="delta",
            color_continuous_scale=["#2a915f", "#efefdf", "#c44844"],
        )
        fig.update_layout(xaxis_title="Sensore", yaxis_title=f"Delta {selected_pollutant.upper()}")
        st.plotly_chart(fig, width="stretch")
        st.dataframe(
            scenario_snapshot[
                ["sensor_name", "zone", "estimated_value", "scenario_value", "delta", "traffic_index", "green_index"]
            ].sort_values("delta"),
            width="stretch",
            hide_index=True,
        )

with tab_timeseries:
    sensor_names = sorted(estimates["sensor_name"].dropna().unique()) if not estimates.empty else []
    selected_sensor = st.selectbox("Sensore", sensor_names, index=0 if sensor_names else None)
    subset = estimates[(estimates["pollutant"] == selected_pollutant) & (estimates["sensor_name"] == selected_sensor)]
    if subset.empty:
        st.warning("Nessuna serie temporale disponibile.")
    else:
        fig = px.line(subset.sort_values("timestamp"), x="timestamp", y="estimated_value", markers=False)
        fig.add_vline(x=selected_timestamp, line_width=2, line_dash="dot", line_color="#2a915f")
        fig.update_layout(yaxis_title=f"{selected_pollutant.upper()} stimato", xaxis_title="Ora")
        st.plotly_chart(fig, width="stretch")

with tab_quality:
    st.subheader("Qualita e provenienza dati")
    if estimates.empty:
        st.warning("Nessun dataset stimato caricato.")
    else:
        st.metric("Righe stime campus", f"{len(estimates):,}")
        st.metric("Righe ARPAC caricate", f"{len(read_table(settings.processed_dir / 'air_quality_observations.parquet')):,}")
        st.metric("Stazioni ARPAC", f"{len(stations):,}")
        st.write("Ultimo download/modello:", estimates["downloaded_at"].max())
        synthetic_share = estimates["is_synthetic"].fillna(False).mean() * 100
        st.write(f"Quota righe basate su fallback sintetico: {synthetic_share:.1f}%")
    warnings = schema_report.get("warnings", [])
    if warnings:
        st.write("Avvisi schema/provenienza")
        st.json(warnings)
    else:
        st.success("Nessun avviso schema registrato.")
    inspection_path = settings.processed_dir / "unisa_weather_inspection.json"
    if inspection_path.exists():
        st.write("Ispezione pagina meteo UNISA")
        st.json(json.loads(inspection_path.read_text(encoding="utf-8")))
