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
    build_reliability_grid,
    color_zone_geojson,
    sensor_snapshot,
    summarize_by_zone,
    timestamp_window,
    value_color,
    window_frame,
    zone_delta_summary,
)
from unisa_air_twin.model import estimate_campus_air_quality
from unisa_air_twin.scenario import apply_scenario, scenario_summary
from unisa_air_twin.sensors import create_virtual_sensors
from unisa_air_twin.storage import geojson_points_to_frame, read_geojson, read_table
from unisa_air_twin.utils import read_json
from unisa_air_twin.validation import leave_one_station_out_validation
from unisa_air_twin.zones import ensure_twin_layers

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
    .guide-box {
        border-left: 3px solid #2a915f;
        padding: 0.7rem 0.9rem;
        background: rgba(42, 145, 95, 0.065);
        margin: 0.4rem 0 0.8rem 0;
    }
    .warning-box {
        border-left: 3px solid #b95b42;
        padding: 0.7rem 0.9rem;
        background: rgba(185, 91, 66, 0.07);
        margin: 0.4rem 0 0.8rem 0;
    }
    .legend-row {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin: 0.22rem 0;
        font-size: 0.9rem;
    }
    .legend-swatch {
        width: 1.15rem;
        height: 0.72rem;
        border-radius: 2px;
        border: 1px solid rgba(0,0,0,0.16);
        display: inline-block;
    }
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
def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict, dict[str, dict], dict, dict, pd.DataFrame, dict]:
    settings = load_settings()
    sensors = geojson_points_to_frame(settings.processed_dir / "campus_virtual_sensors.geojson")
    if sensors.empty:
        sensors = create_virtual_sensors(settings)
    if not (settings.processed_dir / "campus_zones.geojson").exists():
        ensure_twin_layers(settings)
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
    zones_geojson = read_geojson(settings.processed_dir / "campus_zones.geojson")
    entities = read_json(settings.processed_dir / "digital_twin_entities.json", default={"entities": []})
    validation = read_table(settings.processed_dir / "model_validation.parquet")
    validation_summary = read_json(
        settings.processed_dir / "model_validation_summary.json",
        default={"rows": 0, "overall": {"mae": None, "bias": None}, "by_pollutant": []},
    )
    if validation.empty and not estimates.empty and not stations.empty:
        validation = leave_one_station_out_validation(settings)
        validation_summary = read_json(
            settings.processed_dir / "model_validation_summary.json",
            default={"rows": 0, "overall": {"mae": None, "bias": None}, "by_pollutant": []},
        )
    return (
        estimates,
        sensors,
        stations,
        schema_report if isinstance(schema_report, dict) else {"warnings": []},
        layers,
        zones_geojson,
        entities if isinstance(entities, dict) else {"entities": []},
        validation,
        validation_summary if isinstance(validation_summary, dict) else {"rows": 0, "by_pollutant": []},
    )


def color_series(values: pd.Series, palette: str = "value") -> list[list[int]]:
    if values.empty:
        return []
    low = float(values.min())
    high = float(values.max())
    return [value_color(float(value), low, high, palette=palette) for value in values]


def build_base_layers(osm_layers: dict[str, dict], toggles: dict[str, bool], zones_geojson: dict | None = None) -> list[pdk.Layer]:
    layers: list[pdk.Layer] = []
    if toggles.get("zones") and zones_geojson:
        layers.append(
            pdk.Layer(
                "GeoJsonLayer",
                zones_geojson,
                stroked=True,
                filled=True,
                get_fill_color=[42, 145, 95, 28],
                get_line_color=[42, 145, 95, 160],
                line_width_min_pixels=2,
                pickable=True,
            )
        )
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


def zone_layer(zone_geojson: dict, tooltip_value: str | None = None) -> pdk.Layer:
    return pdk.Layer(
        "GeoJsonLayer",
        zone_geojson,
        stroked=True,
        filled=True,
        get_fill_color="properties.fill_color",
        get_line_color=[45, 50, 56, 165],
        line_width_min_pixels=2,
        pickable=True,
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


def render_legend(delta: bool = False) -> None:
    if delta:
        rows = [
            ("#2a915f", "miglioramento stimato"),
            ("#efefdf", "variazione piccola"),
            ("#c44844", "peggioramento stimato"),
            ("#2346a5", "stazione ARPAC"),
        ]
    else:
        rows = [
            ("#2d845f", "valori più bassi"),
            ("#f0b241", "valori intermedi"),
            ("#c8493d", "valori più alti"),
            ("#2346a5", "stazione ARPAC"),
        ]
    html = "".join(
        f"<div class='legend-row'><span class='legend-swatch' style='background:{color}'></span>{label}</div>"
        for color, label in rows
    )
    st.markdown(html, unsafe_allow_html=True)


def render_disclaimer() -> None:
    st.markdown(
        """
        <div class="warning-box">
        Questo prototipo non fornisce misure ufficiali e non sostituisce ARPAC.
        Usalo per esplorare scenari e comprendere relazioni spaziali, non per decisioni sanitarie o regolatorie.
        </div>
        """,
        unsafe_allow_html=True,
    )


def format_zone(zone: str) -> str:
    labels = {
        "all": "tutto il campus",
        "amministrazione": "amministrazione",
        "didattica": "didattica",
        "mobilita": "mobilità",
        "parcheggio": "parcheggio",
        "servizi": "servizi",
        "studio": "studio",
        "verde": "verde",
    }
    return labels.get(zone, zone)


settings = load_settings()
estimates, sensors, stations, schema_report, osm_layers, zones_geojson, twin_entities, validation, validation_summary = load_data()
pollutants = sorted(estimates["pollutant"].dropna().unique()) if not estimates.empty else ["pm10"]

with st.sidebar:
    st.header("Controlli GIS")
    st.caption("Scegli cosa osservare, poi leggi mappa e scenario come confronto tra alternative.")
    selected_pollutant = st.selectbox(
        "Inquinante",
        pollutants,
        index=0,
        help="PM10 e PM2.5 sono polveri sottili. NO2 è spesso legato al traffico. O3 può crescere nelle ore calde e soleggiate.",
    )
    timestamps = available_timestamps(estimates, selected_pollutant)
    timestamp_labels = [pd.Timestamp(ts).strftime("%Y-%m-%d %H:%M") for ts in timestamps]
    selected_label = st.select_slider(
        "Ora simulata",
        options=timestamp_labels,
        value=timestamp_labels[-1] if timestamp_labels else None,
        help="Sposta il cursore per vedere come cambiano mappa e serie temporali nel tempo.",
    )
    selected_timestamp = pd.Timestamp(selected_label) if selected_label else pd.Timestamp.now().floor("h")
    grid_resolution = st.slider(
        "Risoluzione griglia",
        14,
        34,
        24,
        step=2,
        help="Controlla il dettaglio della heatmap. Valori più alti sono più dettagliati ma possono essere più lenti.",
    )
    st.divider()
    st.caption("Layer mappa")
    layer_toggles = {
        "heatmap": st.checkbox(
            "Heatmap interpolata",
            value=True,
            help="Superficie stimata dai sensori virtuali. Non è una misura continua reale.",
        ),
        "zones": st.checkbox(
            "Zone funzionali",
            value=True,
            help="Poligoni sintetici che rappresentano aree operative del Digital Twin: mobilità, parcheggi, didattica, verde e servizi.",
        ),
        "reliability": st.checkbox(
            "Affidabilità spaziale",
            value=False,
            help="Layer dimostrativo: affidabilità più alta vicino ai sensori virtuali, più bassa lontano dai punti.",
        ),
        "sensors": st.checkbox(
            "Sensori virtuali",
            value=True,
            help="Punti simulati su luoghi rilevanti del campus.",
        ),
        "stations": st.checkbox(
            "Stazioni ARPAC",
            value=True,
            help="Stazioni ufficiali disponibili nei dati ARPAC, quando hanno coordinate.",
        ),
        "buildings": st.checkbox("Edifici", value=True, help="Edifici da OpenStreetMap."),
        "roads": st.checkbox("Strade", value=True, help="Rete stradale da OpenStreetMap."),
        "green": st.checkbox("Aree verdi", value=True, help="Aree verdi e naturali da OpenStreetMap."),
        "transport": st.checkbox(
            "Trasporto pubblico",
            value=True,
            help="Fermate o punti di trasporto pubblico disponibili in OpenStreetMap.",
        ),
        "parking": st.checkbox("Parcheggi", value=True, help="Aree parcheggio disponibili in OpenStreetMap."),
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

tab_gis, tab_scenario, tab_twin, tab_timeseries, tab_guide, tab_quality = st.tabs(
    [
        "GIS operativo",
        "Scenario builder",
        "Digital Twin",
        "Serie temporali",
        "Guida e metodologia",
        "Qualità dati",
    ]
)

with tab_gis:
    left, right = st.columns([3, 1])
    with right:
        if not snapshot.empty:
            st.metric("Media sensori", f"{snapshot['estimated_value'].mean():.1f}")
            st.metric("Massimo", f"{snapshot['estimated_value'].max():.1f}")
            st.metric("Minimo", f"{snapshot['estimated_value'].min():.1f}")
            if "uncertainty_score" in snapshot.columns:
                st.metric("Incertezza media", f"{snapshot['uncertainty_score'].mean():.2f}")
        st.markdown(
            "<p class='small-note'>La superficie continua e ottenuta con interpolazione IDW sui sensori virtuali del campus.</p>",
            unsafe_allow_html=True,
        )
        st.subheader("Legenda")
        render_legend(delta=False)
        with st.expander("Come leggere questa mappa"):
            st.write(
                "La mappa mostra una stima dimostrativa per l'ora selezionata. "
                "I colori aiutano a confrontare zone del campus: non rappresentano misure ufficiali punto-per-punto."
            )
            st.write(
                "I sensori virtuali sono i punti più importanti da leggere. "
                "La heatmap riempie lo spazio tra questi punti con una interpolazione semplice."
            )
            st.write(
                "Le zone funzionali trasformano la dashboard in un simulatore GIS: gli scenari possono essere letti per area, non solo per singolo sensore."
            )
    with left:
        if snapshot.empty:
            st.warning("Nessun dato disponibile per l'ora selezionata.")
        else:
            map_layers = build_base_layers(osm_layers, layer_toggles, zones_geojson)
            grid = build_interpolation_grid(snapshot, resolution=grid_resolution)
            reliability_grid = build_reliability_grid(snapshot, resolution=grid_resolution)
            if layer_toggles["heatmap"] and not grid.empty:
                map_layers.append(grid_layer(grid, "estimated_value"))
            if layer_toggles["reliability"] and not reliability_grid.empty:
                map_layers.append(grid_layer(reliability_grid, "reliability"))
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
                        "confidence_label",
                        "nearest_station_km",
                    ]
                ].sort_values("estimated_value", ascending=False),
                width="stretch",
                hide_index=True,
            )

with tab_scenario:
    st.markdown(
        """
        <div class="guide-box">
        Costruisci uno scenario spaziale: scegli dove agisce, cosa cambia e per quale finestra temporale.
        La mappa Delta mostra l'effetto stimato per sensori e zone funzionali.
        </div>
        """,
        unsafe_allow_html=True,
    )
    scenario_mode = st.radio(
        "Modalità",
        ["Scenario guidato", "Confronto preset"],
        horizontal=True,
        help="Usa Scenario guidato per costruire una simulazione. Usa Confronto preset per confrontare rapidamente alternative.",
    )
    window_label = st.selectbox(
        "Quando applicare lo scenario",
        ["Solo ora selezionata", "Mattina", "Pranzo", "Pomeriggio", "Giornata intera"],
        help="La finestra temporale serve per leggere l'effetto nel tempo, non solo sulla singola ora.",
    )
    scenario_timestamps = timestamp_window(timestamps, selected_timestamp, window_label)
    scenario_window = window_frame(estimates, selected_pollutant, scenario_timestamps)
    preset_options = [
        "Personalizzato",
        "Ora di punta al terminal bus",
        "Parcheggio meno utilizzato",
        "Giornata di pioggia",
        "Vento forte",
        "Campus green mobility",
        "Nuova area verde nei parcheggi",
    ]
    preset_values = {
        "Personalizzato": (0.2, 1.0, False, "all", 0.0),
        "Ora di punta al terminal bus": (0.45, 1.0, False, "mobilita", 0.0),
        "Parcheggio meno utilizzato": (0.35, 1.0, False, "parcheggio", 0.05),
        "Giornata di pioggia": (0.1, 1.0, True, "all", 0.0),
        "Vento forte": (0.0, 1.8, False, "all", 0.0),
        "Campus green mobility": (0.35, 1.1, False, "all", 0.25),
        "Nuova area verde nei parcheggi": (0.15, 1.0, False, "parcheggio", 0.4),
    }

    if scenario_mode == "Confronto preset":
        comparison_rows = []
        for name in preset_options[1:]:
            traffic, wind, rain, zone, green = preset_values[name]
            candidate = apply_scenario(
                snapshot,
                settings,
                traffic_reduction=traffic,
                wind_multiplier=wind,
                rain_event=rain,
                focus_zone=zone,
                green_improvement=green,
            )
            summary = scenario_summary(candidate)
            comparison_rows.append(
                {
                    "scenario": name,
                    "zona": format_zone(zone),
                    "delta_medio": summary["mean_delta"],
                    "miglioramento_massimo": summary["min_delta"],
                    "sensori_migliorati": summary["improved_sensors"],
                }
            )
        comparison = pd.DataFrame(comparison_rows)
        fig = px.bar(
            comparison.sort_values("delta_medio"),
            x="scenario",
            y="delta_medio",
            color="delta_medio",
            color_continuous_scale=["#2a915f", "#efefdf", "#c44844"],
        )
        fig.update_layout(xaxis_title="Scenario", yaxis_title=f"Delta medio {selected_pollutant.upper()}")
        st.plotly_chart(fig, width="stretch")
        st.dataframe(comparison.sort_values("delta_medio"), width="stretch", hide_index=True)
    else:
        preset = st.selectbox(
            "Scenario",
            preset_options,
            help="I preset sono esempi narrativi. Puoi sempre modificarli con gli slider sotto.",
        )
        default_traffic, default_wind, default_rain, default_zone, default_green = preset_values[preset]
        control_a, control_b, control_c, control_d = st.columns(4)
        traffic_reduction = control_a.slider(
            "Riduzione traffico",
            0,
            50,
            int(default_traffic * 100),
            step=5,
            help="Percentuale ipotetica di riduzione del contributo traffico nel modello.",
        ) / 100
        wind_multiplier = control_b.slider(
            "Moltiplicatore vento",
            0.5,
            2.0,
            float(default_wind),
            step=0.1,
            help="Valori maggiori simulano vento più forte. Nel modello il vento disperde PM e NO2.",
        )
        focus_zone = control_c.selectbox(
            "Zona intervento",
            zones,
            index=zones.index(default_zone) if default_zone in zones else 0,
            format_func=format_zone,
            help="Applica l'intervento soprattutto a una zona del campus. 'all' applica lo scenario ovunque.",
        )
        green_improvement = control_d.slider(
            "Verde aggiunto",
            0,
            50,
            int(default_green * 100),
            step=5,
            help="Proxy semplificato: aumenta l'effetto mitigante associato alle aree verdi.",
        ) / 100
        rain_event = st.toggle(
            "Evento di pioggia",
            value=default_rain,
            help="Nel MVP la pioggia riduce soprattutto PM10 e PM2.5.",
        )

        scenario_snapshot = apply_scenario(
            snapshot,
            settings,
            traffic_reduction=traffic_reduction,
            wind_multiplier=wind_multiplier,
            rain_event=rain_event,
            focus_zone=focus_zone,
            green_improvement=green_improvement,
        )
        scenario_window_result = apply_scenario(
            scenario_window,
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
            zone_summary = zone_delta_summary(scenario_snapshot)
            zone_delta_geojson = color_zone_geojson(zones_geojson, zone_summary, "mean_delta")
            summary = scenario_summary(scenario_snapshot)
            metric_a, metric_b, metric_c, metric_d = st.columns(4)
            metric_a.metric("Delta medio", f"{summary['mean_delta']:+.2f}")
            metric_b.metric("Miglioramento massimo", f"{summary['min_delta']:+.2f}")
            metric_c.metric("Sensori migliorati", f"{summary['improved_sensors']}/{len(scenario_snapshot)}")
            metric_d.metric("Finestra", f"{len(scenario_timestamps)} ore")

            map_a, map_b = st.columns(2)
            with map_a:
                st.subheader("Scenario")
                scenario_layers = build_base_layers(osm_layers, layer_toggles, zones_geojson)
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
                st.subheader("Delta per zona")
                render_legend(delta=True)
                delta_layers = build_base_layers(osm_layers, {**layer_toggles, "zones": False}, zones_geojson)
                delta_layers.append(zone_layer(zone_delta_geojson if not zone_summary.empty else zones_geojson))
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
                            "html": "<b>{name}</b><br/>Zona: {zone}<br/>Delta medio: {mean_delta}",
                            "style": {"backgroundColor": "white", "color": "black"},
                        },
                    ),
                    width="stretch",
                )

            if not scenario_window_result.empty:
                timeline = (
                    scenario_window_result.groupby("timestamp", as_index=False)
                    .agg(baseline=("estimated_value", "mean"), scenario=("scenario_value", "mean"))
                    .sort_values("timestamp")
                )
                timeline_long = timeline.melt(
                    id_vars="timestamp",
                    value_vars=["baseline", "scenario"],
                    var_name="serie",
                    value_name="valore",
                )
                fig_timeline = px.line(timeline_long, x="timestamp", y="valore", color="serie", markers=True)
                fig_timeline.update_layout(
                    xaxis_title="Ora",
                    yaxis_title=f"{selected_pollutant.upper()} medio sui sensori",
                )
                st.plotly_chart(fig_timeline, width="stretch")

            st.subheader("Componenti del modello")
            component_sensor = st.selectbox(
                "Sensore da spiegare",
                sorted(scenario_snapshot["sensor_name"].unique()),
                help="Mostra quanto pesano base ARPAC, traffico, verde e meteo nel valore finale.",
            )
            component_row = scenario_snapshot[scenario_snapshot["sensor_name"] == component_sensor].iloc[0]
            components = pd.DataFrame(
                [
                    {"componente": "Base ARPAC IDW", "valore": component_row["base_value"]},
                    {"componente": "Traffico", "valore": component_row["traffic_component"]},
                    {"componente": "Verde", "valore": -component_row["green_component"]},
                    {"componente": "Meteo", "valore": component_row["weather_component"]},
                ]
            )
            fig_components = px.bar(
                components,
                x="componente",
                y="valore",
                color="valore",
                color_continuous_scale=["#2a915f", "#efefdf", "#c44844"],
            )
            fig_components.update_layout(xaxis_title="", yaxis_title="Contributo")
            st.plotly_chart(fig_components, width="stretch")

            st.dataframe(
                scenario_snapshot[
                    [
                        "sensor_name",
                        "zone",
                        "estimated_value",
                        "scenario_value",
                        "delta",
                        "traffic_index",
                        "green_index",
                        "confidence_label",
                        "uncertainty_score",
                    ]
                ].sort_values("delta"),
                width="stretch",
                hide_index=True,
            )
            if not zone_summary.empty:
                st.subheader("Delta aggregato per zona")
                zone_summary_display = zone_summary.copy()
                zone_summary_display["zona"] = zone_summary_display["zone"].map(format_zone)
                st.dataframe(
                    zone_summary_display[["zona", "mean_delta", "min_delta", "max_delta", "sensors"]].sort_values(
                        "mean_delta"
                    ),
                    width="stretch",
                    hide_index=True,
                )
            with st.expander("Come interpretare lo scenario"):
                st.write(
                    "La baseline è il valore stimato prima dello scenario. "
                    "Lo scenario è il valore dopo le modifiche ipotetiche. "
                    "Il delta è scenario meno baseline."
                )
                st.write(
                    "Un delta negativo indica riduzione stimata dell'inquinante; "
                    "un delta positivo indica aumento stimato. Il risultato serve a confrontare alternative, non a certificare un effetto reale."
                )

with tab_twin:
    st.markdown(
        """
        <div class="guide-box">
        Questa vista espone gli asset del Digital Twin: zone, sensori virtuali, geometrie e affidabilità spaziale.
        È pensata per ragionare sul campus come sistema di entità, non solo come grafico ambientale.
        </div>
        """,
        unsafe_allow_html=True,
    )
    entity_rows = []
    for entity in twin_entities.get("entities", []):
        entity_rows.append(
            {
                "id": entity.get("id"),
                "type": entity.get("type"),
                "name": entity.get("name"),
                "zone": format_zone(entity.get("zone", "")),
                "description": (entity.get("properties") or {}).get("description", ""),
            }
        )
    entity_df = pd.DataFrame(entity_rows)
    metric_a, metric_b, metric_c = st.columns(3)
    metric_a.metric("Entità Digital Twin", f"{len(entity_df):,}")
    metric_b.metric("Zone funzionali", f"{int((entity_df['type'] == 'CampusZone').sum()) if not entity_df.empty else 0}")
    metric_c.metric(
        "Sensori virtuali",
        f"{int((entity_df['type'] == 'VirtualSensor').sum()) if not entity_df.empty else 0}",
    )

    twin_map_a, twin_map_b = st.columns(2)
    with twin_map_a:
        st.subheader("Asset spaziali")
        zone_value_summary = summarize_by_zone(snapshot, "estimated_value")
        zone_value_geojson = color_zone_geojson(zones_geojson, zone_value_summary, "mean_value")
        twin_layers = build_base_layers(osm_layers, {**layer_toggles, "zones": False}, zones_geojson)
        twin_layers.append(zone_layer(zone_value_geojson))
        if layer_toggles["sensors"]:
            twin_layers.append(sensor_layer(snapshot, "estimated_value"))
        st.pydeck_chart(
            deck(
                twin_layers,
                {
                    "html": "<b>{name}</b><br/>Zona: {zone}<br/>Valore medio: {mean_value}",
                    "style": {"backgroundColor": "white", "color": "black"},
                },
            ),
            width="stretch",
        )
    with twin_map_b:
        st.subheader("Affidabilità spaziale")
        reliability_grid = build_reliability_grid(snapshot, resolution=grid_resolution)
        reliability_layers = build_base_layers(osm_layers, {**layer_toggles, "zones": True}, zones_geojson)
        if not reliability_grid.empty:
            reliability_layers.append(grid_layer(reliability_grid, "reliability"))
        if layer_toggles["sensors"]:
            reliability_layers.append(sensor_layer(snapshot, "estimated_value"))
        st.pydeck_chart(
            deck(
                reliability_layers,
                {
                    "html": "Affidabilità: {reliability}<br/>Distanza sensore: {nearest_sensor_km} km",
                    "style": {"backgroundColor": "white", "color": "black"},
                },
            ),
            width="stretch",
        )
        st.caption(
            "Layer dimostrativo: l'affidabilità è maggiore vicino ai sensori virtuali e minore nelle aree più lontane."
        )

    if not entity_df.empty:
        selected_entity = st.selectbox(
            "Scheda entità",
            entity_df["id"].tolist(),
            format_func=lambda entity_id: entity_df.loc[entity_df["id"] == entity_id, "name"].iloc[0],
        )
        selected_row = entity_df[entity_df["id"] == selected_entity].iloc[0]
        st.markdown(f"**{selected_row['name']}** · `{selected_row['type']}` · zona {selected_row['zone']}")
        st.write(selected_row["description"])
        st.dataframe(entity_df.sort_values(["type", "name"]), width="stretch", hide_index=True)

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

with tab_guide:
    render_disclaimer()
    st.subheader("Percorso consigliato")
    step_a, step_b, step_c = st.columns(3)
    with step_a:
        st.markdown("**1. Osserva**")
        st.write("Scegli inquinante e ora dalla barra laterale, poi guarda sensori e heatmap.")
    with step_b:
        st.markdown("**2. Simula**")
        st.write("Apri un preset what-if e modifica traffico, vento, pioggia o zona.")
    with step_c:
        st.markdown("**3. Confronta**")
        st.write("Leggi la mappa Delta: verde significa miglioramento stimato, rosso peggioramento stimato.")

    st.subheader("Concetti chiave")
    with st.expander("Cos'è un Digital Twin in questo MVP?", expanded=True):
        st.write(
            "È una rappresentazione digitale del campus che unisce dati ambientali, mappe GIS, "
            "sensori virtuali e scenari. In questo MVP non replica tutta la fisica atmosferica: "
            "serve a esplorare dati, luoghi e ipotesi in modo interattivo."
        )
    with st.expander("Cosa sono i sensori virtuali?"):
        st.write(
            "Sono punti simulati collocati in aree riconoscibili del campus, come terminal bus, parcheggio, mensa e area verde. "
            "Non sono strumenti fisici. Servono a costruire una prima griglia di osservazione locale."
        )
    with st.expander("Cosa significa heatmap?"):
        st.write(
            "La heatmap colora una superficie continua sul campus. Viene calcolata interpolando i valori dei sensori virtuali. "
            "Aiuta a vedere pattern spaziali, ma non è una misura diretta in ogni punto della mappa."
        )
    with st.expander("Cosa significa delta?"):
        st.write(
            "Il delta è la differenza tra scenario e baseline. Se il delta è negativo, lo scenario riduce il valore stimato. "
            "Se è positivo, lo aumenta."
        )

    st.subheader("Metodo in breve")
    st.markdown(
        """
        ```text
        valore stimato =
            base ARPAC interpolata
            + effetto traffico
            - effetto verde
            + effetto meteo
        ```
        """
    )
    method_a, method_b = st.columns(2)
    with method_a:
        st.markdown("**Fonti dati**")
        st.write("ARPAC fornisce i dati ufficiali regionali. Open-Meteo fornisce il meteo quando UNISA non espone un endpoint stabile. OpenStreetMap fornisce layer GIS.")
        st.markdown("**IDW**")
        st.write("L'interpolazione IDW assegna più peso ai punti vicini e meno peso a quelli lontani.")
    with method_b:
        st.markdown("**Scenario what-if**")
        st.write("Gli slider non cambiano dati reali: modificano componenti del modello per confrontare alternative.")
        st.markdown("**Limite principale**")
        st.write("Il traffico è un proxy orario, non un conteggio reale di veicoli o persone.")

    st.subheader("Documentazione")
    st.write("Guida utente: `docs/USER_GUIDE.md`")
    st.write("Metodologia tecnica: `docs/METHODOLOGY.md`")

with tab_quality:
    st.subheader("Qualità e provenienza dati")
    if estimates.empty:
        st.warning("Nessun dataset stimato caricato.")
    else:
        st.metric("Righe stime campus", f"{len(estimates):,}")
        st.metric("Righe ARPAC caricate", f"{len(read_table(settings.processed_dir / 'air_quality_observations.parquet')):,}")
        st.metric("Stazioni ARPAC", f"{len(stations):,}")
        st.write("Ultimo download/modello:", estimates["downloaded_at"].max())
        synthetic_share = estimates["is_synthetic"].fillna(False).mean() * 100
        st.write(f"Quota righe basate su fallback sintetico: {synthetic_share:.1f}%")
        if "confidence_label" in estimates.columns:
            st.write("Distribuzione confidenza stime")
            st.dataframe(
                estimates["confidence_label"]
                .fillna("non disponibile")
                .value_counts()
                .rename_axis("confidenza")
                .reset_index(name="righe"),
                width="stretch",
                hide_index=True,
            )
    st.subheader("Validazione open-data")
    validation_rows = int(validation_summary.get("rows", 0) or 0)
    if validation_rows:
        overall = validation_summary.get("overall", {})
        val_a, val_b, val_c = st.columns(3)
        val_a.metric("Righe validazione", f"{validation_rows:,}")
        val_b.metric("MAE medio", f"{overall.get('mae'):.2f}" if overall.get("mae") is not None else "n/d")
        val_c.metric("Bias medio", f"{overall.get('bias'):+.2f}" if overall.get("bias") is not None else "n/d")
        by_pollutant = pd.DataFrame(validation_summary.get("by_pollutant", []))
        if not by_pollutant.empty:
            st.dataframe(by_pollutant, width="stretch", hide_index=True)
        with st.expander("Metodo di validazione"):
            st.write(
                "La validazione usa solo dati ARPAC open: per ogni ora e inquinante, una stazione viene esclusa, "
                "il valore viene ricostruito dalle altre stazioni con IDW e poi confrontato con il valore osservato."
            )
    else:
        st.info("Validazione non disponibile: servono almeno due stazioni ARPAC con coordinate e valori nello stesso orario.")
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
