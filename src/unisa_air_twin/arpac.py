from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

from unisa_air_twin.config import Settings
from unisa_air_twin.logging_utils import get_logger
from unisa_air_twin.utils import (
    ensure_dir,
    first_existing_column,
    normalize_column_name,
    normalize_columns,
    read_csv_flexible,
    safe_to_parquet,
    utc_now_iso,
    write_json,
    write_schema_report,
)

LOGGER = get_logger(__name__)

TIMESTAMP_CANDIDATES = [
    "data",
    "datamisura",
    "data_misura",
    "data_ora",
    "data_rilevazione",
    "datetime",
    "timestamp",
    "date",
]
STATION_CANDIDATES = [
    "stazione",
    "nome_stazione",
    "station",
    "station_name",
    "codice_stazione",
    "id_stazione",
]
POLLUTANT_CANDIDATES = {
    "pm10": ["pm10", "pm_10"],
    "pm25": ["pm2.5", "pm25", "pm_2_5", "pm2_5"],
    "no2": ["no2", "biossido_di_azoto"],
    "o3": ["o3", "ozono"],
}
POLLUTANT_VALID_RANGES = {
    "pm10": (0.0, 500.0),
    "pm25": (0.0, 500.0),
    "no2": (0.0, 500.0),
    "o3": (0.0, 500.0),
}
LONG_POLLUTANT_CANDIDATES = ["inquinante", "pollutant", "parametro", "codice_inquinante"]
LONG_VALUE_CANDIDATES = ["valore", "value", "concentrazione", "misura", "media"]


@dataclass
class Resource:
    name: str
    url: str
    dataset_id: str
    kind: str


def _request_json(url: str) -> dict | None:
    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        payload = response.json()
        if payload.get("success") and payload.get("result"):
            return payload
    except Exception as exc:
        LOGGER.warning("CKAN request failed for %s: %s", url, exc)
    return None


def _discover_ckan_resources(dataset_id: str, kind: str) -> list[Resource]:
    endpoints = [
        f"https://dati.arpacampania.it/api/3/action/package_show?id={dataset_id}",
        f"https://dati.arpacampania.it/it/api/3/action/package_show?id={dataset_id}",
        f"https://dati.arpacampania.it/en/api/3/action/package_show?id={dataset_id}",
    ]
    for endpoint in endpoints:
        payload = _request_json(endpoint)
        if not payload:
            continue
        resources = []
        for item in payload["result"].get("resources", []):
            url = item.get("url") or ""
            fmt = (item.get("format") or "").lower()
            if "csv" in fmt or ".csv" in url.lower():
                resources.append(
                    Resource(
                        name=item.get("name") or Path(urlparse(url).path).name,
                        url=url,
                        dataset_id=dataset_id,
                        kind=kind,
                    )
                )
        if resources:
            return resources
    return []


def _discover_html_resources(page_url: str, dataset_id: str, kind: str) -> list[Resource]:
    try:
        response = requests.get(page_url, timeout=20)
        response.raise_for_status()
    except Exception as exc:
        LOGGER.warning("Could not scrape ARPAC page %s: %s", page_url, exc)
        return []
    soup = BeautifulSoup(response.text, "html.parser")
    resources: list[Resource] = []
    for link in soup.find_all("a", href=True):
        href = str(link["href"])
        if ".csv" not in href.lower() and "download" not in href.lower():
            continue
        url = requests.compat.urljoin(page_url, href)
        resources.append(
            Resource(
                name=link.get_text(" ", strip=True) or Path(urlparse(url).path).name,
                url=url,
                dataset_id=dataset_id,
                kind=kind,
            )
        )
    return resources


def discover_resources(settings: Settings) -> list[Resource]:
    discovered: list[Resource] = []
    for dataset in settings.arpac["datasets"]:
        dataset_id = dataset["id"]
        kind = dataset["kind"]
        resources = _discover_ckan_resources(dataset_id, kind)
        if not resources:
            resources = _discover_html_resources(dataset["page_url"], dataset_id, kind)
        LOGGER.info("Discovered %s CSV resources for ARPAC dataset %s", len(resources), dataset_id)
        discovered.extend(resources)
    return discovered


def _resource_sort_key(resource: Resource) -> tuple[int, int, str]:
    text = f"{resource.name} {resource.url}"
    matches = re.findall(r"(20\d{2})[-_/]?(0[1-9]|1[0-2])?", text)
    if not matches:
        return (0, 0, text)
    year, month = matches[-1]
    return (int(year), int(month or 1), text)


def select_recent_resources(resources: list[Resource], limit_per_dataset: int) -> list[Resource]:
    selected: list[Resource] = []
    by_dataset: dict[str, list[Resource]] = {}
    for resource in resources:
        by_dataset.setdefault(resource.dataset_id, []).append(resource)
    for dataset_resources in by_dataset.values():
        selected.extend(sorted(dataset_resources, key=_resource_sort_key, reverse=True)[:limit_per_dataset])
    return selected


def _safe_filename(resource: Resource) -> str:
    parsed_name = Path(urlparse(resource.url).path).name or resource.name
    if not parsed_name.lower().endswith(".csv"):
        parsed_name = f"{parsed_name}.csv"
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", parsed_name)
    return f"{resource.kind}_{safe_name}"


def download_arpac(settings: Settings, force: bool = False, months: int | None = None) -> list[dict]:
    raw_dir = ensure_dir(settings.raw_dir / "arpac")
    resources = discover_resources(settings)
    if not resources:
        resources = [
            Resource(
                name="metadati-stazioni-rqa-1.csv",
                url=settings.arpac["station_metadata_url"],
                dataset_id="fallback_station_metadata",
                kind="station_metadata",
            )
        ]
    limit = months or int(settings.arpac.get("resource_limit_per_dataset", 1))
    selected = select_recent_resources(resources, limit)
    manifest: list[dict] = []
    for resource in selected:
        target = raw_dir / _safe_filename(resource)
        if target.exists() and not force:
            LOGGER.info("Using cached ARPAC file %s", target)
        else:
            try:
                response = requests.get(resource.url, timeout=60)
                response.raise_for_status()
                target.write_bytes(response.content)
                LOGGER.info("Downloaded ARPAC resource %s", resource.url)
            except Exception as exc:
                LOGGER.warning("ARPAC download failed for %s: %s", resource.url, exc)
                continue
        manifest.append(
            {
                "dataset_id": resource.dataset_id,
                "kind": resource.kind,
                "name": resource.name,
                "url": resource.url,
                "path": str(target),
                "downloaded_at": utc_now_iso(),
            }
        )
    write_json(raw_dir / "manifest.json", manifest)
    return manifest


def _parse_timestamp(df: pd.DataFrame, timestamp_col: str) -> pd.Series:
    raw_values = df[timestamp_col].astype(str)
    iso_like = raw_values.str.match(r"^\d{4}-\d{2}-\d{2}").mean() > 0.5
    timestamps = pd.to_datetime(df[timestamp_col], errors="coerce", dayfirst=not iso_like, utc=True)
    if timestamps.notna().any():
        return timestamps.dt.tz_convert(None)
    timestamps = pd.to_datetime(df[timestamp_col], errors="coerce", utc=True)
    return timestamps.dt.tz_convert(None)


def _clean_single_observation_file(path: Path, source_url: str | None = None) -> tuple[pd.DataFrame, list[dict]]:
    warnings: list[dict] = []
    try:
        raw = normalize_columns(read_csv_flexible(path))
    except Exception as exc:
        return pd.DataFrame(), [{"file": str(path), "warning": f"Could not read CSV: {exc}"}]
    timestamp_col = first_existing_column(raw.columns, TIMESTAMP_CANDIDATES)
    station_col = first_existing_column(raw.columns, STATION_CANDIDATES)
    if not timestamp_col or not station_col:
        warnings.append(
            {
                "file": str(path),
                "columns": list(raw.columns),
                "warning": "Could not identify timestamp and station columns for observations.",
            }
        )
        return pd.DataFrame(), warnings
    cleaned = pd.DataFrame(
        {
            "timestamp": _parse_timestamp(raw, timestamp_col),
            "station_id": raw[station_col].astype(str).str.strip(),
            "station_name": raw[station_col].astype(str).str.strip(),
        }
    )
    found_pollutants: list[str] = []
    for pollutant, candidates in POLLUTANT_CANDIDATES.items():
        column = first_existing_column(raw.columns, candidates)
        if column:
            cleaned[pollutant] = pd.to_numeric(raw[column], errors="coerce")
            found_pollutants.append(pollutant)
    pollutant_col = first_existing_column(raw.columns, LONG_POLLUTANT_CANDIDATES)
    value_col = first_existing_column(raw.columns, LONG_VALUE_CANDIDATES)
    if not found_pollutants and pollutant_col and value_col:
        long_df = cleaned[["timestamp", "station_id", "station_name"]].copy()
        long_df["pollutant"] = raw[pollutant_col].map(normalize_column_name)
        long_df["value"] = pd.to_numeric(raw[value_col], errors="coerce")
        cleaned = (
            long_df.pivot_table(
                index=["timestamp", "station_id", "station_name"],
                columns="pollutant",
                values="value",
                aggfunc="mean",
            )
            .reset_index()
            .rename_axis(None, axis=1)
        )
        for pollutant in POLLUTANT_CANDIDATES:
            if pollutant in cleaned.columns:
                found_pollutants.append(pollutant)
    if not found_pollutants:
        warnings.append(
            {
                "file": str(path),
                "columns": list(raw.columns),
                "warning": "Could not map pollutant columns. Expected PM10, PM2.5, NO2, or O3.",
            }
        )
        return pd.DataFrame(), warnings
    cleaned = cleaned.dropna(subset=["timestamp"])
    cleaned["source"] = "arpac"
    cleaned["source_url"] = source_url or ""
    cleaned["downloaded_at"] = utc_now_iso()
    cleaned["is_synthetic"] = False
    keep = ["timestamp", "station_id", "station_name", *POLLUTANT_CANDIDATES, "source", "source_url", "downloaded_at", "is_synthetic"]
    for column in keep:
        if column not in cleaned.columns:
            cleaned[column] = pd.NA
    for pollutant, (low, high) in POLLUTANT_VALID_RANGES.items():
        if pollutant in cleaned.columns:
            values = pd.to_numeric(cleaned[pollutant], errors="coerce")
            cleaned[pollutant] = values.where(values.between(low, high))
    return cleaned[keep], warnings


def _synthetic_station_metadata() -> pd.DataFrame:
    downloaded_at = utc_now_iso()
    rows = [
        ("ARPAC_SALERNO_FALLBACK", "Salerno synthetic fallback", 40.681, 14.768),
        ("ARPAC_BARONISSI_FALLBACK", "Baronissi synthetic fallback", 40.748, 14.770),
        ("ARPAC_AVELLINO_FALLBACK", "Avellino synthetic fallback", 40.914, 14.789),
    ]
    return pd.DataFrame(
        [
            {
                "station_id": station_id,
                "station_name": name,
                "lat": lat,
                "lon": lon,
                "source": "synthetic_fallback",
                "source_url": "",
                "downloaded_at": downloaded_at,
                "is_synthetic": True,
            }
            for station_id, name, lat, lon in rows
        ]
    )


def synthetic_air_quality_observations() -> pd.DataFrame:
    stations = _synthetic_station_metadata()
    timestamps = pd.date_range(end=pd.Timestamp.now().floor("h"), periods=96, freq="h")
    rows: list[dict] = []
    for station_index, station in stations.iterrows():
        for timestamp in timestamps:
            hour = timestamp.hour
            rush = 1 if hour in {8, 9, 17, 18} and timestamp.weekday() < 5 else 0
            rows.append(
                {
                    "timestamp": timestamp,
                    "station_id": station["station_id"],
                    "station_name": station["station_name"],
                    "pm10": 18 + station_index * 2 + rush * 5 + max(0, 5 - abs(hour - 8)) * 0.3,
                    "pm25": 10 + station_index + rush * 2.5,
                    "no2": 22 + station_index * 3 + rush * 9,
                    "o3": 48 + max(0, 14 - abs(hour - 14)) * 1.1 - rush * 2,
                    "source": "synthetic_fallback",
                    "source_url": "",
                    "downloaded_at": utc_now_iso(),
                    "is_synthetic": True,
                }
            )
    return pd.DataFrame(rows)


def _read_station_metadata_file(path: Path) -> pd.DataFrame:
    raw_text = path.read_text(encoding="utf-8", errors="replace")
    lines = [line for line in raw_text.splitlines() if line.strip()]
    if not lines:
        return pd.DataFrame()
    header = lines[0].split(",")
    if "Codice Europeo" not in header or "Latitudine" not in header or "Longitudine" not in header:
        return normalize_columns(read_csv_flexible(path))
    expected_columns = len(header)
    fixed_prefix_columns = 7
    fixed_suffix_columns = expected_columns - fixed_prefix_columns - 1
    rows: list[list[str]] = []
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) < expected_columns:
            continue
        prefix = parts[:fixed_prefix_columns]
        address = ",".join(parts[fixed_prefix_columns : len(parts) - fixed_suffix_columns]).strip()
        suffix = parts[-fixed_suffix_columns:]
        rows.append([*prefix, address, *suffix])
    return normalize_columns(pd.DataFrame(rows, columns=header))


def _coordinate_series(raw: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(raw[column].astype(str).str.replace(",", ".", regex=False), errors="coerce")


def clean_station_metadata(settings: Settings) -> pd.DataFrame:
    raw_dir = settings.raw_dir / "arpac"
    metadata_files = sorted(raw_dir.glob("*station*.csv")) + sorted(raw_dir.glob("*stazioni*.csv")) + sorted(raw_dir.glob("*metadata*.csv"))
    warnings: list[dict] = []
    for path in metadata_files:
        try:
            raw = _read_station_metadata_file(path)
        except Exception as exc:
            warnings.append({"file": str(path), "warning": f"Could not read station metadata: {exc}"})
            continue
        station_col = first_existing_column(
            raw.columns,
            ["codice_europeo", "codice_arpac", "codice_nazionale", *STATION_CANDIDATES],
        )
        name_col = first_existing_column(raw.columns, ["nome", "nome_stazione", "stazione", "station_name"])
        lat_col = first_existing_column(raw.columns, ["lat", "latitude", "latitudine", "y"])
        lon_col = first_existing_column(raw.columns, ["lon", "lng", "longitude", "longitudine", "x"])
        if not station_col or not lat_col or not lon_col:
            warnings.append(
                {
                    "file": str(path),
                    "columns": list(raw.columns),
                    "warning": "Could not identify station id and coordinate columns.",
                }
            )
            continue
        lat = _coordinate_series(raw, lat_col)
        lon = _coordinate_series(raw, lon_col)
        df = pd.DataFrame(
            {
                "station_id": raw[station_col].astype(str).str.strip(),
                "station_name": raw[name_col].astype(str).str.strip() if name_col else raw[station_col].astype(str),
                "lat": lat,
                "lon": lon,
                "source": "arpac",
                "source_url": settings.arpac["station_metadata_url"],
                "downloaded_at": utc_now_iso(),
                "is_synthetic": False,
            }
        ).dropna(subset=["lat", "lon"])
        df = df[df["lat"].between(39.0, 42.5) & df["lon"].between(13.0, 16.5)]
        if not df.empty:
            return df
    if warnings:
        write_schema_report(settings.processed_dir, warnings)
    LOGGER.warning("No usable ARPAC station metadata found. Creating labeled synthetic fallback.")
    return _synthetic_station_metadata()


def clean_air_quality(settings: Settings) -> pd.DataFrame:
    raw_dir = settings.raw_dir / "arpac"
    manifest_path = raw_dir / "manifest.json"
    manifest = []
    if manifest_path.exists():
        try:
            manifest = pd.read_json(manifest_path).to_dict(orient="records")
        except Exception:
            manifest = []
    source_by_path = {item.get("path"): item.get("url") for item in manifest}
    frames: list[pd.DataFrame] = []
    warnings: list[dict] = []
    for path in sorted(raw_dir.glob("*.csv")):
        if any(word in path.name.lower() for word in ["stazioni", "metadata", "metadati", "rete"]):
            continue
        frame, file_warnings = _clean_single_observation_file(path, source_by_path.get(str(path)))
        warnings.extend(file_warnings)
        if not frame.empty:
            frames.append(frame)
    if warnings:
        write_schema_report(settings.processed_dir, warnings)
    if not frames:
        LOGGER.warning("No usable ARPAC observations found. Creating labeled synthetic fallback.")
        observations = synthetic_air_quality_observations()
    else:
        observations = pd.concat(frames, ignore_index=True).sort_values("timestamp")
    safe_to_parquet(observations, settings.processed_dir / "air_quality_observations.parquet")
    station_metadata = clean_station_metadata(settings)
    safe_to_parquet(station_metadata, settings.processed_dir / "arpac_station_metadata.parquet")
    return observations
