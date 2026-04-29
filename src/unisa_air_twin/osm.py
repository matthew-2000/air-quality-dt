from __future__ import annotations

import json
from pathlib import Path

from unisa_air_twin.config import Settings
from unisa_air_twin.logging_utils import get_logger
from unisa_air_twin.utils import ensure_dir, utc_now_iso

LOGGER = get_logger(__name__)


def _feature_collection(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": features}


def _point_feature(lon: float, lat: float, properties: dict) -> dict:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": properties,
    }


def _polygon_feature(points: list[tuple[float, float]], properties: dict) -> dict:
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [[list(point) for point in points]]},
        "properties": properties,
    }


def _line_feature(points: list[tuple[float, float]], properties: dict) -> dict:
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": [list(point) for point in points]},
        "properties": properties,
    }


def _write_geojson(path: Path, payload: dict) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _fallback_geojson(settings: Settings) -> None:
    lat = settings.campus["fallback_latitude"]
    lon = settings.campus["fallback_longitude"]
    processed = settings.processed_dir
    provenance = {
        "source": "offline_placeholder",
        "source_url": "OpenStreetMap unavailable in local run",
        "downloaded_at": utc_now_iso(),
        "is_real": False,
    }
    _write_geojson(
        processed / "campus_buildings.geojson",
        _feature_collection(
            [
                _polygon_feature(
                    [
                        (lon - 0.004, lat - 0.002),
                        (lon - 0.002, lat - 0.002),
                        (lon - 0.002, lat),
                        (lon - 0.004, lat),
                        (lon - 0.004, lat - 0.002),
                    ],
                    {"name": "Campus buildings fallback", **provenance},
                )
            ]
        ),
    )
    _write_geojson(
        processed / "campus_roads.geojson",
        _feature_collection(
            [
                _line_feature(
                    [(lon - 0.012, lat - 0.004), (lon, lat + 0.002), (lon + 0.012, lat + 0.004)],
                    {"name": "Campus drive road fallback", **provenance},
                )
            ]
        ),
    )
    _write_geojson(
        processed / "campus_green.geojson",
        _feature_collection(
            [
                _polygon_feature(
                    [
                        (lon + 0.002, lat - 0.004),
                        (lon + 0.010, lat - 0.004),
                        (lon + 0.010, lat + 0.004),
                        (lon + 0.002, lat + 0.004),
                        (lon + 0.002, lat - 0.004),
                    ],
                    {"name": "Campus green fallback", **provenance},
                )
            ]
        ),
    )
    _write_geojson(
        processed / "campus_transport.geojson",
        _feature_collection([_point_feature(lon - 0.005, lat - 0.003, {"name": "Terminal bus fallback", **provenance})]),
    )
    _write_geojson(
        processed / "campus_parking.geojson",
        _feature_collection([_point_feature(lon - 0.007, lat - 0.004, {"name": "Parking fallback", **provenance})]),
    )


def download_osm(settings: Settings, force: bool = False) -> None:
    expected_outputs = [
        settings.processed_dir / "campus_buildings.geojson",
        settings.processed_dir / "campus_roads.geojson",
        settings.processed_dir / "campus_green.geojson",
        settings.processed_dir / "campus_transport.geojson",
        settings.processed_dir / "campus_parking.geojson",
    ]
    if all(path.exists() for path in expected_outputs) and not force:
        LOGGER.info("Using cached OSM campus layers.")
        return
    try:
        import osmnx as ox

        place_name = settings.campus["place_name"]
        tags_buildings = {"building": True}
        tags_green = {"leisure": ["park", "garden"], "landuse": ["grass", "forest", "meadow"], "natural": True}
        tags_transport = {"highway": ["bus_stop"], "public_transport": True}
        tags_parking = {"amenity": "parking"}

        outputs = [
            ("campus_buildings.geojson", tags_buildings),
            ("campus_green.geojson", tags_green),
            ("campus_transport.geojson", tags_transport),
            ("campus_parking.geojson", tags_parking),
        ]
        for filename, tags in outputs:
            try:
                gdf = ox.features_from_place(place_name, tags=tags)
            except Exception:
                lat = settings.campus["fallback_latitude"]
                lon = settings.campus["fallback_longitude"]
                distance = settings.campus["fallback_distance_m"]
                gdf = ox.features_from_point((lat, lon), tags=tags, dist=distance)
            gdf = gdf.reset_index()
            gdf["source"] = "openstreetmap"
            gdf["source_url"] = "https://www.openstreetmap.org/"
            gdf["downloaded_at"] = utc_now_iso()
            gdf["is_real"] = True
            gdf.to_file(settings.processed_dir / filename, driver="GeoJSON")

        graph = ox.graph_from_place(place_name, network_type="drive", simplify=True)
        _, edges = ox.graph_to_gdfs(graph)
        edges = edges.reset_index()
        edges["source"] = "openstreetmap"
        edges["source_url"] = "https://www.openstreetmap.org/"
        edges["downloaded_at"] = utc_now_iso()
        edges["is_real"] = True
        edges.to_file(settings.processed_dir / "campus_roads.geojson", driver="GeoJSON")
        LOGGER.info("Downloaded OSM campus layers.")
    except Exception as exc:
        LOGGER.warning("OSM download failed or dependencies unavailable: %s", exc)
        _fallback_geojson(settings)
