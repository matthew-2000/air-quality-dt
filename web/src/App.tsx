import {
  Activity,
  AlertTriangle,
  CloudRain,
  Layers,
  Map,
  RefreshCcw,
  SlidersHorizontal,
  Wind,
} from "lucide-react";
import { useEffect, useMemo, useState, useTransition } from "react";

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

function collectPoints(mapData?: MapPayload, scenario?: ScenarioPayload): LatLon[] {
  const points: LatLon[] = [];
  mapData?.snapshot.forEach((sensor) => points.push(sensor));
  mapData?.stations.forEach((station) => points.push(station));
  mapData?.grid.forEach((cell) => cell.polygon.forEach(([lon, lat]) => points.push({ lat, lon })));
  scenario?.delta_grid.forEach((cell) => cell.polygon.forEach(([lon, lat]) => points.push({ lat, lon })));
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

function CampusMap({
  mapData,
  scenario,
  mode,
}: {
  mapData?: MapPayload;
  scenario?: ScenarioPayload;
  mode: "baseline" | "delta";
}) {
  const projection = useProjection(mapData, scenario);
  const grid = mode === "delta" ? scenario?.delta_grid : mapData?.grid;
  const zones = mode === "delta" ? scenario?.zone_delta_geojson : mapData?.zones;
  const sensors = mode === "delta" && scenario?.snapshot.length ? scenario.snapshot : mapData?.snapshot ?? [];
  const zonePaths = featurePaths(zones, projection.project);
  const roadPaths = featurePaths(mapData?.layers.roads, projection.project);
  const buildingPaths = featurePaths(mapData?.layers.buildings, projection.project);
  const greenPaths = featurePaths(mapData?.layers.green, projection.project);

  return (
    <div className="map-shell">
      <svg className="campus-map" viewBox="0 0 100 100" role="img" aria-label="Campus air quality map">
        <rect width="100" height="100" fill="#e9ece5" />
        {greenPaths.map((item) => (
          <path key={`green-${item.key}`} d={item.path} className="geo-green" />
        ))}
        {buildingPaths.map((item) => (
          <path key={`building-${item.key}`} d={item.path} className="geo-building" />
        ))}
        {roadPaths.map((item) => (
          <path key={`road-${item.key}`} d={item.path} className="geo-road" />
        ))}
        {grid?.map((cell, index) => {
          const path = cell.polygon
            .map(([lon, lat], pointIndex) => {
              const [x, y] = projection.project({ lon, lat });
              return `${pointIndex === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
            })
            .join(" ")
            .concat(" Z");
          return <path key={`grid-${index}`} d={path} fill={rgba(cell.color, mode === "delta" ? 0.85 : 0.78)} />;
        })}
        {zonePaths.map((item) => {
          const fill = item.properties?.fill_color as [number, number, number, number] | undefined;
          return (
            <path
              key={`zone-${item.key}`}
              d={item.path}
              fill={fill ? rgba(fill, 0.8) : "transparent"}
              className="zone-outline"
            />
          );
        })}
        {mapData?.stations.map((station, index) => {
          const [x, y] = projection.project(station);
          return <circle key={`station-${index}`} cx={x} cy={y} r="1.35" className="station-dot" />;
        })}
        {sensors.map((sensor, index) => {
          const [x, y] = projection.project(sensor);
          const delta = sensor.delta ?? 0;
          const className = mode === "delta" ? (delta < 0 ? "sensor-dot improved" : "sensor-dot worse") : "sensor-dot";
          return (
            <g key={`${sensor.sensor_name}-${index}`}>
              <circle cx={x} cy={y} r="1.85" className={className} />
              <title>{`${sensor.sensor_name}: ${(sensor.scenario_value ?? sensor.estimated_value).toFixed(2)}`}</title>
            </g>
          );
        })}
      </svg>
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

function App() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [timestamps, setTimestamps] = useState<string[]>([]);
  const [pollutant, setPollutant] = useState("pm10");
  const [timestamp, setTimestamp] = useState<string | null>(null);
  const [mapData, setMapData] = useState<MapPayload>();
  const [scenario, setScenario] = useState<ScenarioPayload>();
  const [mode, setMode] = useState<"baseline" | "delta">("baseline");
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
    setControls((current) => ({ ...current, ...presetControls }));
  };

  const topSensors = useMemo(() => {
    const source = mode === "delta" && scenario?.snapshot.length ? scenario.snapshot : mapData?.snapshot ?? [];
    return [...source]
      .sort((a, b) => (mode === "delta" ? (a.delta ?? 0) - (b.delta ?? 0) : b.estimated_value - a.estimated_value))
      .slice(0, 5);
  }, [mapData, mode, scenario]);

  return (
    <main className="app">
      <aside className="sidebar">
        <div>
          <p className="eyebrow">UNISA Air Twin</p>
          <h1>Operazioni ambientali campus</h1>
        </div>

        <section className="control-group">
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
          <button className={mode === "delta" ? "active" : ""} onClick={() => setMode("delta")}>
            <Activity size={16} /> Delta
          </button>
        </section>

        <section className="control-group scenario-controls">
          <div className="section-title">
            <SlidersHorizontal size={16} />
            Scenario
          </div>
          <select onChange={(event) => selectedPreset(event.target.value)} defaultValue="Personalizzato">
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
              onChange={(event) => setControls({ ...controls, traffic_reduction: Number(event.target.value) })}
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
              onChange={(event) => setControls({ ...controls, wind_multiplier: Number(event.target.value) })}
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
              onChange={(event) => setControls({ ...controls, green_improvement: Number(event.target.value) })}
            />
          </label>
          <label>
            Zona
            <select
              value={controls.focus_zone}
              onChange={(event) => setControls({ ...controls, focus_zone: event.target.value })}
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
              onChange={(event) => setControls({ ...controls, window_label: event.target.value })}
            >
              {windows.map((item) => (
                <option key={item}>{item}</option>
              ))}
            </select>
          </label>
          <button
            className={controls.rain_event ? "rain-toggle active" : "rain-toggle"}
            onClick={() => setControls({ ...controls, rain_event: !controls.rain_event })}
          >
            <CloudRain size={16} /> Evento pioggia
          </button>
        </section>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <p>{summary?.campus.name ?? "Campus di Fisciano"}</p>
            <strong>{pollutant.toUpperCase()} · {formatTime(timestamp)}</strong>
          </div>
          <div className="status-actions">
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
          <div className="map-caption">
            <Layers size={16} />
            {mode === "delta" ? "Delta scenario per sensore e zona" : "Baseline IDW su sensori virtuali"}
          </div>
        </div>
      </section>

      <aside className="inspector">
        <section className="metrics-grid">
          <div>
            <span>Delta medio</span>
            <strong>{scenario?.summary.mean_delta.toFixed(2) ?? "n/d"}</strong>
          </div>
          <div>
            <span>Sensori migliorati</span>
            <strong>
              {scenario ? `${scenario.summary.improved_sensors}/${scenario.summary.rows}` : "n/d"}
            </strong>
          </div>
          <div>
            <span>Righe modello</span>
            <strong>{summary?.rows.toLocaleString("it-IT") ?? "n/d"}</strong>
          </div>
          <div>
            <span>Stazioni ARPAC</span>
            <strong>{summary?.stations ?? "n/d"}</strong>
          </div>
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
              <div key={sensor.sensor_name} className="sensor-row">
                <div>
                  <strong>{sensor.sensor_name}</strong>
                  <span>{sensor.zone}</span>
                </div>
                <b>
                  {mode === "delta" && sensor.delta !== undefined
                    ? `${sensor.delta > 0 ? "+" : ""}${sensor.delta.toFixed(2)}`
                    : sensor.estimated_value.toFixed(1)}
                </b>
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
