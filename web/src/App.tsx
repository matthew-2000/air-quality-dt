import {
  Activity,
  AlertTriangle,
  BarChart3,
  CloudRain,
  Compass,
  Gauge,
  Leaf,
  Layers,
  Map,
  RadioTower,
  RefreshCcw,
  Route,
  SlidersHorizontal,
  Wind,
} from "lucide-react";
import * as L from "leaflet";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState, useTransition } from "react";
import { CircleMarker, GeoJSON, MapContainer, Polygon, Popup, TileLayer, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

type LatLon = { lat: number; lon: number };
type GeoFeature = {
  geometry: { type: string; coordinates: unknown } | null;
  properties?: Record<string, unknown> | null;
};
type FeatureCollection = { type?: string; features: GeoFeature[] };
type Sensor = LatLon & {
  sensor_name: string;
  zone: string;
  estimated_value: number;
  scenario_value?: number;
  delta?: number;
  confidence_label?: string;
};
type GridCell = {
  polygon: [number, number][];
  color: [number, number, number, number];
  estimated_value?: number;
  scenario_value?: number;
  delta_value?: number;
};
type Preset = {
  name: string;
  traffic_reduction: number;
  wind_multiplier: number;
  rain_event: boolean;
  focus_zone: string;
  green_improvement: number;
};
type Summary = {
  project: string;
  campus: { name: string; latitude: number; longitude: number };
  pollutants: string[];
  default_pollutant: string;
  latest_timestamp: string | null;
  rows: number;
  stations: number;
  zones: { id: string; label: string }[];
  presets: Preset[];
  validation: { rows?: number; overall?: { mae?: number; bias?: number } };
  warnings: unknown[];
};
type MapPayload = {
  snapshot: Sensor[];
  grid: GridCell[];
  reliability_grid: GridCell[];
  zones: FeatureCollection;
  layers: Record<string, FeatureCollection>;
  stations: (LatLon & { station_name?: string; name?: string })[];
};
type ScenarioPayload = {
  summary: { mean_delta: number; min_delta: number; max_delta: number; improved_sensors: number; rows: number };
  snapshot: Sensor[];
  scenario_grid: GridCell[];
  delta_grid: GridCell[];
  zone_summary: { zone: string; mean_delta: number; min_delta: number; max_delta: number; sensors: number }[];
  zone_delta_geojson: FeatureCollection;
  timeline: { timestamp: string; baseline: number; scenario: number }[];
};
type ScenarioControls = {
  traffic_reduction: number;
  wind_multiplier: number;
  rain_event: boolean;
  focus_zone: string;
  green_improvement: number;
  window_label: string;
};
type MapMode = "baseline" | "scenario" | "delta";

const windows = ["Solo ora selezionata", "Mattina", "Pranzo", "Pomeriggio", "Giornata intera"];

async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

function rgba(color: [number, number, number, number], alphaScale = 1) {
  return `rgba(${color[0]}, ${color[1]}, ${color[2]}, ${(color[3] / 255) * alphaScale})`;
}

function formatTime(value: string | null) {
  if (!value) return "n/d";
  return new Intl.DateTimeFormat("it-IT", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatNumber(value: number | undefined, fractionDigits = 1) {
  if (value === undefined || Number.isNaN(value)) return "n/d";
  return value.toLocaleString("it-IT", {
    maximumFractionDigits: fractionDigits,
    minimumFractionDigits: fractionDigits,
  });
}

function deltaTone(value: number | undefined) {
  if (value === undefined) return "neutral";
  if (value < -0.05) return "good";
  if (value > 0.05) return "bad";
  return "neutral";
}

function collectPoints(mapData?: MapPayload, scenario?: ScenarioPayload): LatLon[] {
  const points: LatLon[] = [];
  mapData?.snapshot.forEach((sensor) => points.push(sensor));
  mapData?.grid.forEach((cell) => cell.polygon.forEach(([lon, lat]) => points.push({ lat, lon })));
  scenario?.delta_grid.forEach((cell) => cell.polygon.forEach(([lon, lat]) => points.push({ lat, lon })));
  Object.values(mapData?.layers ?? {}).forEach((collection) => collectGeoPoints(collection).forEach((point) => points.push(point)));
  collectGeoPoints(mapData?.zones).forEach((point) => points.push(point));
  collectGeoPoints(scenario?.zone_delta_geojson).forEach((point) => points.push(point));
  return points;
}

function collectGeoPoints(collection?: FeatureCollection): LatLon[] {
  const points: LatLon[] = [];
  const visit = (value: unknown) => {
    if (!Array.isArray(value)) return;
    if (value.length >= 2 && typeof value[0] === "number" && typeof value[1] === "number") {
      points.push({ lon: Number(value[0]), lat: Number(value[1]) });
      return;
    }
    value.forEach(visit);
  };
  collection?.features.forEach((feature) => visit(feature.geometry?.coordinates));
  return points;
}

function useProjection(mapData?: MapPayload, scenario?: ScenarioPayload) {
  return useMemo(() => {
    const points = collectPoints(mapData, scenario);
    const fallback = { project: (point: LatLon) => [50, 50] as [number, number], ready: false };
    if (!points.length) return fallback;
    const lats = points.map((point) => point.lat);
    const lons = points.map((point) => point.lon);
    const minLat = Math.min(...lats);
    const maxLat = Math.max(...lats);
    const minLon = Math.min(...lons);
    const maxLon = Math.max(...lons);
    const latSpan = maxLat - minLat || 1;
    const lonSpan = maxLon - minLon || 1;
    return {
      ready: true,
      project(point: LatLon) {
        const x = 6 + ((point.lon - minLon) / lonSpan) * 88;
        const y = 94 - ((point.lat - minLat) / latSpan) * 88;
        return [x, y] as [number, number];
      },
    };
  }, [mapData, scenario]);
}

function polygonPath(coordinates: unknown, project: (point: LatLon) => [number, number]): string {
  if (!Array.isArray(coordinates)) return "";
  const ring = coordinates[0];
  if (!Array.isArray(ring)) return "";
  return ring
    .map((pair, index) => {
      if (!Array.isArray(pair)) return "";
      const [x, y] = project({ lon: Number(pair[0]), lat: Number(pair[1]) });
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ")
    .concat(" Z");
}

function linePath(coordinates: unknown, project: (point: LatLon) => [number, number]): string {
  if (!Array.isArray(coordinates)) return "";
  return coordinates
    .map((pair, index) => {
      if (!Array.isArray(pair)) return "";
      const [x, y] = project({ lon: Number(pair[0]), lat: Number(pair[1]) });
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

function featurePaths(collection: FeatureCollection | undefined, project: (point: LatLon) => [number, number]) {
  if (!collection?.features) return [];
  return collection.features.flatMap((feature, featureIndex) => {
    const geometry = feature.geometry;
    if (!geometry) return [];
    if (geometry.type === "Polygon") {
      return [{ key: `${featureIndex}`, path: polygonPath(geometry.coordinates, project), properties: feature.properties }];
    }
    if (geometry.type === "MultiPolygon") {
      const polygons = Array.isArray(geometry.coordinates) ? geometry.coordinates : [];
      return polygons.map((polygon, polygonIndex) => ({
        key: `${featureIndex}-${polygonIndex}`,
        path: polygonPath(polygon, project),
        properties: feature.properties,
      }));
    }
    if (geometry.type === "LineString") {
      return [{ key: `${featureIndex}`, path: linePath(geometry.coordinates, project), properties: feature.properties }];
    }
    if (geometry.type === "MultiLineString" && Array.isArray(geometry.coordinates)) {
      const lines = geometry.coordinates;
      return lines.map((line, lineIndex) => ({
        key: `${featureIndex}-${lineIndex}`,
        path: linePath(line, project),
        properties: feature.properties,
      }));
    }
    return [];
  });
}

function featurePoints(collection: FeatureCollection | undefined, project: (point: LatLon) => [number, number]) {
  if (!collection?.features) return [];
  return collection.features.flatMap((feature, featureIndex) => {
    const geometry = feature.geometry;
    if (!geometry) return [];
    if (geometry.type === "Point" && Array.isArray(geometry.coordinates)) {
      const [lon, lat] = geometry.coordinates;
      const [x, y] = project({ lon: Number(lon), lat: Number(lat) });
      return [{ key: `${featureIndex}`, x, y, properties: feature.properties }];
    }
    if (geometry.type === "MultiPoint" && Array.isArray(geometry.coordinates)) {
      return geometry.coordinates.map((pair, pointIndex) => {
        const [lon, lat] = Array.isArray(pair) ? pair : [0, 0];
        const [x, y] = project({ lon: Number(lon), lat: Number(lat) });
        return { key: `${featureIndex}-${pointIndex}`, x, y, properties: feature.properties };
      });
    }
    return [];
  });
}

function MapFitBounds({ points }: { points: LatLon[] }) {
  const leafletMap = useMap();

  useEffect(() => {
    if (!points.length) return;
    const bounds = points.map((point) => [point.lat, point.lon] as [number, number]);
    leafletMap.fitBounds(bounds, { padding: [36, 36], maxZoom: 16 });
  }, [leafletMap, points]);

  return null;
}

function CampusMap({
  mapData,
  scenario,
  mode,
}: {
  mapData?: MapPayload;
  scenario?: ScenarioPayload;
  mode: MapMode;
}) {
  const grid = mode === "delta" ? scenario?.delta_grid : mode === "scenario" ? scenario?.scenario_grid : mapData?.grid;
  const zones = mode === "delta" ? scenario?.zone_delta_geojson : mapData?.zones;
  const sensors = mode !== "baseline" && scenario?.snapshot.length ? scenario.snapshot : mapData?.snapshot ?? [];
  const campusPoints = useMemo(() => collectPoints(mapData, scenario), [mapData, scenario]);
  const center: [number, number] = [40.771, 14.79];
  const layerStyle = {
    buildings: { color: "#29342f", weight: 1, fillColor: "#2f3a34", fillOpacity: 0.22, opacity: 0.38 },
    green: { color: "#367e49", weight: 1, fillColor: "#367e49", fillOpacity: 0.24, opacity: 0.35 },
    roads: { color: "#42524a", weight: 2, opacity: 0.68 },
    parking: { color: "#9d7330", weight: 1, fillColor: "#c49b42", fillOpacity: 0.24, opacity: 0.55 },
    transport: { color: "#2f5f9f", weight: 2, fillColor: "#2f5f9f", fillOpacity: 0.22, opacity: 0.74 },
    zones: { color: "#17201c", weight: 2, fillOpacity: mode === "delta" ? 0.2 : 0.07, opacity: 0.52 },
  };

  return (
    <div className="map-shell">
      <MapContainer center={center} zoom={15} scrollWheelZoom className="leaflet-map" zoomControl={false}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <MapFitBounds points={campusPoints} />
        {grid?.map((cell, index) => (
          <Polygon
            key={`grid-${index}`}
            positions={cell.polygon.map(([lon, lat]) => [lat, lon])}
            pathOptions={{
              color: "transparent",
              fillColor: rgba(cell.color, 1),
              fillOpacity: mode === "delta" ? 0.52 : mode === "scenario" ? 0.42 : 0.26,
              weight: 0,
            }}
          />
        ))}
        {mapData?.layers.green ? <GeoJSON key="green" data={mapData.layers.green as never} style={layerStyle.green} /> : null}
        {mapData?.layers.buildings ? (
          <GeoJSON key="buildings" data={mapData.layers.buildings as never} style={layerStyle.buildings} />
        ) : null}
        {mapData?.layers.roads ? <GeoJSON key="roads" data={mapData.layers.roads as never} style={layerStyle.roads} /> : null}
        {mapData?.layers.parking ? (
          <GeoJSON key="parking" data={mapData.layers.parking as never} style={layerStyle.parking} />
        ) : null}
        {mapData?.layers.transport ? (
          <GeoJSON key="transport" data={mapData.layers.transport as never} style={layerStyle.transport} pointToLayer={(_feature, latlng) => L.circleMarker(latlng, { radius: 5, ...layerStyle.transport })} />
        ) : null}
        {zones ? <GeoJSON key={`zones-${mode}`} data={zones as never} style={layerStyle.zones} /> : null}
        {mapData?.stations.map((station, index) => (
          <CircleMarker
            key={`station-${index}`}
            center={[station.lat, station.lon]}
            radius={6}
            pathOptions={{ color: "#ffffff", fillColor: "#2f5f9f", fillOpacity: 0.9, weight: 2 }}
          >
            <Popup>{station.station_name ?? station.name ?? "Stazione ARPAC"}</Popup>
          </CircleMarker>
        ))}
        {sensors.map((sensor, index) => {
          const delta = sensor.delta ?? 0;
          const fillColor = mode === "delta" ? (delta < 0 ? "#2f8060" : "#bd5345") : mode === "scenario" ? "#2f8060" : "#101915";
          return (
            <CircleMarker
              key={`${sensor.sensor_name}-${index}`}
              center={[sensor.lat, sensor.lon]}
              radius={8}
              pathOptions={{ color: "#fffdf4", fillColor, fillOpacity: 0.96, weight: 3 }}
            >
              <Popup>
                <strong>{sensor.sensor_name}</strong>
                <br />
                Zona: {sensor.zone}
                <br />
                Valore: {formatNumber(sensor.scenario_value ?? sensor.estimated_value, 2)}
                {sensor.delta !== undefined ? (
                  <>
                    <br />
                    Delta: {sensor.delta > 0 ? "+" : ""}
                    {formatNumber(sensor.delta, 2)}
                  </>
                ) : null}
              </Popup>
            </CircleMarker>
          );
        })}
      </MapContainer>
    </div>
  );
}

function Timeline({ points }: { points: ScenarioPayload["timeline"] }) {
  const values = points.flatMap((point) => [point.baseline, point.scenario]);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pathFor = (key: "baseline" | "scenario") =>
    points
      .map((point, index) => {
        const x = 4 + (index / Math.max(points.length - 1, 1)) * 92;
        const y = 86 - ((point[key] - min) / span) * 70;
        return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
      })
      .join(" ");

  if (!points.length) return <div className="empty-line">Timeline non disponibile</div>;
  return (
    <svg className="timeline" viewBox="0 0 100 100" role="img" aria-label="Scenario timeline">
      <path d={pathFor("baseline")} className="line baseline" />
      <path d={pathFor("scenario")} className="line scenario" />
    </svg>
  );
}

function MetricTile({
  icon,
  label,
  value,
  hint,
  tone = "neutral",
}: {
  icon: ReactNode;
  label: string;
  value: string;
  hint?: string;
  tone?: "neutral" | "good" | "bad";
}) {
  return (
    <div className={`metric-tile ${tone}`}>
      <div className="metric-icon">{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
      {hint ? <em>{hint}</em> : null}
    </div>
  );
}

function App() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [timestamps, setTimestamps] = useState<string[]>([]);
  const [pollutant, setPollutant] = useState("pm10");
  const [timestamp, setTimestamp] = useState<string | null>(null);
  const [mapData, setMapData] = useState<MapPayload>();
  const [scenario, setScenario] = useState<ScenarioPayload>();
  const [mode, setMode] = useState<MapMode>("baseline");
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const [controls, setControls] = useState<ScenarioControls>({
    traffic_reduction: 0.2,
    wind_multiplier: 1.0,
    rain_event: false,
    focus_zone: "all",
    green_improvement: 0,
    window_label: "Solo ora selezionata",
  });

  useEffect(() => {
    getJson<Summary>("/api/summary")
      .then((payload) => {
        setSummary(payload);
        setPollutant(payload.default_pollutant);
        setTimestamp(payload.latest_timestamp);
        const preset = payload.presets[0];
        if (preset) {
          const { name: _name, ...presetControls } = preset;
          setControls((current) => ({ ...current, ...presetControls }));
        }
      })
      .catch((reason) => setError(reason.message));
  }, []);

  useEffect(() => {
    if (!pollutant) return;
    getJson<{ timestamps: string[] }>(`/api/timestamps?pollutant=${encodeURIComponent(pollutant)}`)
      .then((payload) => {
        setTimestamps(payload.timestamps);
        setTimestamp((current) => (current && payload.timestamps.includes(current) ? current : payload.timestamps.at(-1) ?? null));
      })
      .catch((reason) => setError(reason.message));
  }, [pollutant]);

  useEffect(() => {
    if (!pollutant || !timestamp) return;
    startTransition(() => {
      Promise.all([
        getJson<MapPayload>(`/api/map?pollutant=${pollutant}&timestamp=${encodeURIComponent(timestamp)}&resolution=24`),
        getJson<ScenarioPayload>("/api/scenario", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ pollutant, timestamp, resolution: 24, ...controls }),
        }),
      ])
        .then(([mapPayload, scenarioPayload]) => {
          setMapData(mapPayload);
          setScenario(scenarioPayload);
          setError(null);
        })
        .catch((reason) => setError(reason.message));
    });
  }, [pollutant, timestamp, controls]);

  const selectedPreset = (name: string) => {
    const preset = summary?.presets.find((item) => item.name === name);
    if (!preset) return;
    const { name: _name, ...presetControls } = preset;
    setMode("scenario");
    setControls((current) => ({ ...current, ...presetControls }));
  };

  const updateScenarioControls = (nextControls: ScenarioControls) => {
    setMode("scenario");
    setControls(nextControls);
  };

  const topSensors = useMemo(() => {
    const source = mode !== "baseline" && scenario?.snapshot.length ? scenario.snapshot : mapData?.snapshot ?? [];
    return [...source]
      .sort((a, b) =>
        mode === "delta"
          ? (a.delta ?? 0) - (b.delta ?? 0)
          : (b.scenario_value ?? b.estimated_value) - (a.scenario_value ?? a.estimated_value),
      )
      .slice(0, 5);
  }, [mapData, mode, scenario]);
  const selectedPresetName = useMemo(() => {
    if (!summary?.presets.length) return "Personalizzato";
    const match = summary.presets.find(
      (preset) =>
        preset.traffic_reduction === controls.traffic_reduction &&
        preset.wind_multiplier === controls.wind_multiplier &&
        preset.rain_event === controls.rain_event &&
        preset.focus_zone === controls.focus_zone &&
        preset.green_improvement === controls.green_improvement,
    );
    return match?.name ?? "Personalizzato";
  }, [controls, summary]);
  const bestZone = scenario?.zone_summary
    .filter((zone) => Number.isFinite(zone.mean_delta))
    .sort((a, b) => a.mean_delta - b.mean_delta)[0];

  return (
    <main className="app" data-testid="air-twin-cockpit">
      <aside className="sidebar">
        <div className="brand-block">
          <div className="brand-mark">
            <Leaf size={18} />
          </div>
          <h1>Operazioni ambientali campus</h1>
          <p>UNISA Air Quality Digital Twin</p>
        </div>

        <section className="control-group primary-controls">
          <label>
            Inquinante
            <select value={pollutant} onChange={(event) => setPollutant(event.target.value)}>
              {summary?.pollutants.map((item) => (
                <option key={item} value={item}>
                  {item.toUpperCase()}
                </option>
              ))}
            </select>
          </label>
          <label>
            Ora
            <select value={timestamp ?? ""} onChange={(event) => setTimestamp(event.target.value)}>
              {timestamps.map((item) => (
                <option key={item} value={item}>
                  {formatTime(item)}
                </option>
              ))}
            </select>
          </label>
        </section>

        <section className="mode-switch" aria-label="Map mode">
          <button className={mode === "baseline" ? "active" : ""} onClick={() => setMode("baseline")}>
            <Map size={16} /> Baseline
          </button>
          <button className={mode === "scenario" ? "active" : ""} onClick={() => setMode("scenario")}>
            <Gauge size={16} /> Scenario
          </button>
          <button className={mode === "delta" ? "active" : ""} onClick={() => setMode("delta")}>
            <Activity size={16} /> Delta
          </button>
        </section>

        <section className="control-group scenario-controls">
          <div className="section-title">
            <SlidersHorizontal size={16} />
            Scenario
          </div>
          <select onChange={(event) => selectedPreset(event.target.value)} value={selectedPresetName}>
            {summary?.presets.map((preset) => (
              <option key={preset.name}>{preset.name}</option>
            ))}
          </select>
          <label>
            Riduzione traffico <span>{Math.round(controls.traffic_reduction * 100)}%</span>
          <input
              type="range"
              min="0"
              max="0.5"
              step="0.05"
              value={controls.traffic_reduction}
              onChange={(event) => updateScenarioControls({ ...controls, traffic_reduction: Number(event.target.value) })}
              onInput={(event) => updateScenarioControls({ ...controls, traffic_reduction: Number(event.currentTarget.value) })}
            />
          </label>
          <label>
            <Wind size={14} /> Vento <span>{controls.wind_multiplier.toFixed(1)}x</span>
            <input
              type="range"
              min="0.5"
              max="2"
              step="0.1"
              value={controls.wind_multiplier}
              onChange={(event) => updateScenarioControls({ ...controls, wind_multiplier: Number(event.target.value) })}
              onInput={(event) => updateScenarioControls({ ...controls, wind_multiplier: Number(event.currentTarget.value) })}
            />
          </label>
          <label>
            Verde aggiunto <span>{Math.round(controls.green_improvement * 100)}%</span>
            <input
              type="range"
              min="0"
              max="0.5"
              step="0.05"
              value={controls.green_improvement}
              onChange={(event) => updateScenarioControls({ ...controls, green_improvement: Number(event.target.value) })}
              onInput={(event) => updateScenarioControls({ ...controls, green_improvement: Number(event.currentTarget.value) })}
            />
          </label>
          <label>
            Zona
            <select
              value={controls.focus_zone}
              onChange={(event) => updateScenarioControls({ ...controls, focus_zone: event.target.value })}
            >
              {summary?.zones.map((zone) => (
                <option key={zone.id} value={zone.id}>
                  {zone.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Finestra
            <select
              value={controls.window_label}
              onChange={(event) => updateScenarioControls({ ...controls, window_label: event.target.value })}
            >
              {windows.map((item) => (
                <option key={item}>{item}</option>
              ))}
            </select>
          </label>
          <button
            className={controls.rain_event ? "rain-toggle active" : "rain-toggle"}
            onClick={() => updateScenarioControls({ ...controls, rain_event: !controls.rain_event })}
          >
            <CloudRain size={16} /> Evento pioggia
          </button>
        </section>
        <section className="scenario-readout">
          <div>
            <Route size={16} />
            <span>Traffico -{Math.round(controls.traffic_reduction * 100)}%</span>
          </div>
          <div>
            <Wind size={16} />
            <span>Vento {controls.wind_multiplier.toFixed(1)}x</span>
          </div>
          <div>
            <Leaf size={16} />
            <span>Verde +{Math.round(controls.green_improvement * 100)}%</span>
          </div>
        </section>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <p>{summary?.campus.name ?? "Campus di Fisciano"}</p>
            <strong>{pollutant.toUpperCase()} · {formatTime(timestamp)}</strong>
          </div>
          <div className="status-actions">
            <span className="status-chip">Open data</span>
            <span className="status-chip">{mapData?.snapshot.length ?? 0} sensori</span>
            {isPending && <span className="loading">Aggiornamento</span>}
            <button onClick={() => window.location.reload()} aria-label="Refresh">
              <RefreshCcw size={16} />
            </button>
          </div>
        </header>

        {error ? (
          <div className="error-banner">
            <AlertTriangle size={18} /> {error}
          </div>
        ) : null}

        <div className="map-stage">
          <CampusMap mapData={mapData} scenario={scenario} mode={mode} />
          <div className="map-toolbar" aria-label="Map layers">
            <span className={mode === "baseline" ? "active" : ""}>IDW</span>
            <span>OSM</span>
            <span>ARPAC</span>
            <span className={mode === "scenario" ? "active scenario" : ""}>Scenario</span>
            <span className={mode === "delta" ? "active delta" : ""}>Delta</span>
          </div>
          <div className="map-compass">
            <Compass size={18} />
            <span>N</span>
          </div>
          <div className="map-caption">
            <Layers size={16} />
            {mode === "delta"
              ? "Delta scenario per sensore e zona"
              : mode === "scenario"
                ? "Scenario simulato dopo i controlli"
                : "Baseline IDW su sensori virtuali"}
          </div>
          <div className="map-scale">
            <span />
            <b>500 m</b>
          </div>
        </div>
      </section>

      <aside className="inspector">
        <section className="metrics-grid">
          <MetricTile
            icon={<Gauge size={17} />}
            label="Delta medio"
            value={formatNumber(scenario?.summary.mean_delta, 2)}
            hint={bestZone ? `Zona migliore: ${bestZone.zone}` : undefined}
            tone={deltaTone(scenario?.summary.mean_delta)}
          />
          <MetricTile
            icon={<Activity size={17} />}
            label="Sensori migliorati"
            value={scenario ? `${scenario.summary.improved_sensors}/${scenario.summary.rows}` : "n/d"}
            hint="scenario attivo"
            tone={scenario?.summary.improved_sensors ? "good" : "neutral"}
          />
          <MetricTile
            icon={<BarChart3 size={17} />}
            label="Righe modello"
            value={summary?.rows.toLocaleString("it-IT") ?? "n/d"}
            hint="serie oraria"
          />
          <MetricTile
            icon={<RadioTower size={17} />}
            label="Stazioni ARPAC"
            value={`${summary?.stations ?? "n/d"}`}
            hint="fonte ufficiale"
          />
        </section>

        <section>
          <div className="section-title">Timeline scenario</div>
          <Timeline points={scenario?.timeline ?? []} />
          <div className="legend">
            <span><i className="baseline-swatch" /> baseline</span>
            <span><i className="scenario-swatch" /> scenario</span>
          </div>
        </section>

        <section>
          <div className="section-title">Sensori chiave</div>
          <div className="sensor-list">
            {topSensors.map((sensor) => (
              <div key={sensor.sensor_name} className={`sensor-row ${deltaTone(sensor.delta)}`}>
                <div>
                  <strong>{sensor.sensor_name}</strong>
                  <span>{sensor.zone}</span>
                </div>
                <b>
                  {mode === "delta" && sensor.delta !== undefined
                    ? `${sensor.delta > 0 ? "+" : ""}${sensor.delta.toFixed(2)}`
                    : (sensor.scenario_value ?? sensor.estimated_value).toFixed(1)}
                </b>
              </div>
            ))}
          </div>
        </section>

        <section>
          <div className="section-title">Delta per zona</div>
          <div className="zone-list">
            {(scenario?.zone_summary ?? []).slice(0, 4).map((zone) => (
              <div key={zone.zone} className="zone-row">
                <span>{zone.zone}</span>
                <b>{zone.mean_delta > 0 ? "+" : ""}{zone.mean_delta.toFixed(2)}</b>
                <i style={{ width: `${Math.min(Math.abs(zone.mean_delta) * 34, 100)}%` }} />
              </div>
            ))}
          </div>
        </section>

        <section className="quality-strip">
          <span>Validazione open-data</span>
          <strong>
            {summary?.validation?.overall?.mae !== undefined && summary.validation.overall.mae !== null
              ? `MAE ${summary.validation.overall.mae.toFixed(2)}`
              : "n/d"}
          </strong>
        </section>
      </aside>
    </main>
  );
}

export default App;
