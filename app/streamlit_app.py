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
from unisa_air_twin.model import estimate_campus_air_quality
from unisa_air_twin.scenario import apply_scenario
from unisa_air_twin.sensors import create_virtual_sensors
from unisa_air_twin.storage import geojson_points_to_frame, read_table
from unisa_air_twin.utils import read_json

st.set_page_config(page_title="UNISA Air Quality Digital Twin - MVP", layout="wide")


@st.cache_data(show_spinner=False)
def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    settings = load_settings()
    sensors = geojson_points_to_frame(settings.processed_dir / "campus_virtual_sensors.geojson")
    if sensors.empty:
        sensors = create_virtual_sensors(settings)
    estimates = read_table(settings.processed_dir / "campus_air_quality_estimates.parquet")
    if estimates.empty:
        clean_air_quality(settings)
        estimates = estimate_campus_air_quality(settings)
    stations = read_table(settings.processed_dir / "arpac_station_metadata.parquet")
    schema_report = read_json(settings.processed_dir / "schema_report.json", default={"warnings": []})
    return estimates, sensors, stations, schema_report if isinstance(schema_report, dict) else {"warnings": []}


def latest_wide(estimates: pd.DataFrame) -> pd.DataFrame:
    if estimates.empty:
        return pd.DataFrame()
    latest_timestamp = estimates["timestamp"].max()
    latest = estimates[estimates["timestamp"] == latest_timestamp]
    wide = latest.pivot_table(
        index=["sensor_id", "sensor_name", "lat", "lon", "zone"],
        columns="pollutant",
        values="estimated_value",
        aggfunc="mean",
    ).reset_index()
    return wide.rename_axis(None, axis=1)


def color_scale(values: pd.Series) -> list[list[int]]:
    if values.empty:
        return []
    low = float(values.min())
    high = float(values.max())
    span = high - low or 1.0
    colors = []
    for value in values:
        ratio = (float(value) - low) / span
        colors.append([int(60 + ratio * 190), int(180 - ratio * 120), 80, 190])
    return colors


settings = load_settings()
estimates, sensors, stations, schema_report = load_data()
pollutants = sorted(estimates["pollutant"].dropna().unique()) if not estimates.empty else ["pm10"]

st.title("UNISA Air Quality Digital Twin - MVP")

tab_overview, tab_map, tab_timeseries, tab_scenario, tab_quality = st.tabs(
    ["Overview", "Map", "Time series", "Scenario what-if", "Data quality"]
)

with tab_overview:
    st.subheader("Gemello digitale dimostrativo")
    st.write(
        "Questo MVP integra dati pubblici ARPAC, meteo e OpenStreetMap con sensori virtuali "
        "posizionati nel Campus di Fisciano. Il modello stima in modo trasparente PM10, PM2.5, "
        "NO2 e O3 con interpolazione IDW e semplici correzioni per traffico, verde e meteo."
    )
    st.info(
        "Prototipo dimostrativo: non e una rete di misura ufficiale, non sostituisce ARPAC "
        "e non va usato per decisioni sanitarie o regolatorie."
    )
    st.markdown(
        "- ARPAC Campania Open Data per qualita dell'aria e stazioni\n"
        "- Pagina meteo UNISA ispezionata; fallback Open-Meteo documentato\n"
        "- OpenStreetMap/OSMnx per edifici, strade e layer urbani\n"
        "- Sensori virtuali creati manualmente con coordinate sintetiche marcate"
    )

with tab_map:
    selected_pollutant = st.selectbox("Inquinante", pollutants, index=0, key="map_pollutant")
    latest = latest_wide(estimates)
    if not latest.empty and selected_pollutant in latest.columns:
        latest["selected_value"] = latest[selected_pollutant].fillna(0)
        latest["color"] = color_scale(latest["selected_value"])
        tooltip = {
            "html": "<b>{sensor_name}</b><br/>PM10: {pm10}<br/>PM2.5: {pm25}<br/>NO2: {no2}<br/>O3: {o3}",
            "style": {"backgroundColor": "white", "color": "black"},
        }
        layers = [
            pdk.Layer(
                "ScatterplotLayer",
                latest,
                get_position="[lon, lat]",
                get_radius=65,
                get_fill_color="color",
                pickable=True,
            )
        ]
        station_points = stations.dropna(subset=["lat", "lon"]) if not stations.empty else pd.DataFrame()
        if not station_points.empty:
            layers.append(
                pdk.Layer(
                    "ScatterplotLayer",
                    station_points,
                    get_position="[lon, lat]",
                    get_radius=90,
                    get_fill_color=[40, 80, 200, 120],
                    pickable=True,
                )
            )
        deck = pdk.Deck(
            map_style="light",
            initial_view_state=pdk.ViewState(
                latitude=float(settings.campus["fallback_latitude"]),
                longitude=float(settings.campus["fallback_longitude"]),
                zoom=14,
                pitch=0,
            ),
            layers=layers,
            tooltip=tooltip,
        )
        st.pydeck_chart(deck, use_container_width=True)
        st.dataframe(latest[["sensor_name", "zone", selected_pollutant]].sort_values(selected_pollutant, ascending=False))
    else:
        st.warning("Nessuna stima disponibile per la mappa.")

with tab_timeseries:
    col_a, col_b = st.columns(2)
    selected_pollutant = col_a.selectbox("Inquinante", pollutants, index=0, key="ts_pollutant")
    sensor_names = sorted(estimates["sensor_name"].dropna().unique()) if not estimates.empty else []
    selected_sensor = col_b.selectbox("Sensore", sensor_names, index=0 if sensor_names else None)
    subset = estimates[(estimates["pollutant"] == selected_pollutant) & (estimates["sensor_name"] == selected_sensor)]
    if subset.empty:
        st.warning("Nessuna serie temporale disponibile.")
    else:
        fig = px.line(subset.sort_values("timestamp"), x="timestamp", y="estimated_value", markers=True)
        fig.update_layout(yaxis_title=f"{selected_pollutant.upper()} stimato", xaxis_title="Ora")
        st.plotly_chart(fig, use_container_width=True)

with tab_scenario:
    selected_pollutant = st.selectbox("Inquinante", pollutants, index=0, key="scenario_pollutant")
    traffic_reduction = st.slider("Riduzione traffico", 0, 50, 20, step=5) / 100
    wind_multiplier = st.slider("Moltiplicatore vento", 0.5, 2.0, 1.0, step=0.1)
    rain_event = st.toggle("Evento di pioggia", value=False)
    scenario_df = apply_scenario(
        estimates[estimates["pollutant"] == selected_pollutant],
        settings,
        traffic_reduction=traffic_reduction,
        wind_multiplier=wind_multiplier,
        rain_event=rain_event,
    )
    if scenario_df.empty:
        st.warning("Scenario non disponibile.")
    else:
        latest_ts = scenario_df["timestamp"].max()
        latest_scenario = scenario_df[scenario_df["timestamp"] == latest_ts].copy()
        fig = px.bar(
            latest_scenario.sort_values("delta"),
            x="sensor_name",
            y=["estimated_value", "scenario_value"],
            barmode="group",
        )
        fig.update_layout(xaxis_title="Sensore", yaxis_title=f"{selected_pollutant.upper()} stimato")
        st.plotly_chart(fig, use_container_width=True)
        latest_scenario["color"] = [
            [30, 150, 80, 190] if delta <= 0 else [210, 80, 60, 190]
            for delta in latest_scenario["delta"]
        ]
        st.pydeck_chart(
            pdk.Deck(
                map_style="light",
                initial_view_state=pdk.ViewState(
                    latitude=float(settings.campus["fallback_latitude"]),
                    longitude=float(settings.campus["fallback_longitude"]),
                    zoom=14,
                ),
                layers=[
                    pdk.Layer(
                        "ScatterplotLayer",
                        latest_scenario,
                        get_position="[lon, lat]",
                        get_radius=70,
                        get_fill_color="color",
                        pickable=True,
                    )
                ],
                tooltip={"html": "<b>{sensor_name}</b><br/>Delta: {delta}"},
            ),
            use_container_width=True,
        )
        st.dataframe(
            latest_scenario[
                ["sensor_name", "estimated_value", "scenario_value", "delta", "traffic_index", "wind_speed_10m"]
            ].sort_values("delta")
        )

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

