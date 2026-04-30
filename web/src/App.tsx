import {
  Activity,
  Archive,
  Clock3,
  Database,
  Droplets,
  Gauge,
  Leaf,
  Map as MapIcon,
  MapPin,
  RadioTower,
  RefreshCcw,
  Search,
  Thermometer,
  Trees,
} from "lucide-react";
import * as L from "leaflet";
import { useDeferredValue, useEffect, useMemo, useState, useTransition } from "react";
import type { ReactNode } from "react";
import { CircleMarker, GeoJSON, MapContainer, Polygon, Popup, ScaleControl, TileLayer, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

type LatLon = { lat: number; lon: number };
type GeoFeature = {
  geometry: { type: string; coordinates: unknown } | null;
  properties?: Record<string, unknown> | null;
};
type FeatureCollection = { type?: string; features: GeoFeature[] };
type CoverageRow = {
  pollutant: string;
  active_sensors: number;
  capable_sensors: number;
  coverage_ratio: number;
};
type Summary = {
  project: string;
  source?: string;
  campus: { name: string; latitude: number; longitude: number };
  pollutants: string[];
  default_pollutant: string;
  latest_timestamp: string | null;
  latest_received_at?: string | null;
  rows: number;
  raw_rows?: number;
  snapshot_rows?: number;
  sensors: number;
  active_sensors?: number;
  capable_sensors?: number;
  coverage_ratio?: number;
  coverage_by_pollutant: CoverageRow[];
  layer_counts?: Record<string, number>;
  ingestion?: {
    raw_rows?: number;
    snapshot_rows?: number;
    sensors?: number;
    source?: string;
    generated_at?: string;
    snapshot_bucket_minutes?: number;
    snapshot_freshness_minutes?: number;
  };
  warnings: unknown[];
  mode?: string;
};
type SnapshotSensor = LatLon & {
  sensor_id: string;
  sensor_name: string;
  estimated_value: number;
  measured_at?: string | null;
  received_at?: string | null;
  reading_age_seconds?: number;
  reading_age_minutes?: number;
  confidence_label?: string;
  humidity?: number | null;
  temperature?: number | null;
  num_devices_sniffed?: number | null;
  status?: string;
};
type GridCell = {
  polygon: [number, number][];
  color: [number, number, number, number];
  estimated_value?: number;
  reliability?: number;
};
type MapPayload = {
  snapshot: SnapshotSensor[];
  grid: GridCell[];
  reliability_grid: GridCell[];
  zones: FeatureCollection;
  layers: Record<string, FeatureCollection>;
  stations: LatLon[];
  meta?: {
    active_sensors: number;
    capable_sensors: number;
    coverage_ratio: number;
    fresh_sensors: number;
    recent_sensors: number;
    aging_sensors: number;
    median_age_seconds: number;
    min_value?: number | null;
    max_value?: number | null;
  };
};
type HistoryPoint = {
  timestamp: string;
  estimated_value: number;
  temperature?: number | null;
  humidity?: number | null;
  num_devices_sniffed?: number | null;
};
type SensorMetric = {
  pollutant: string;
  estimated_value: number;
  measured_at?: string | null;
  received_at?: string | null;
  reading_age_seconds?: number;
  confidence_label?: string;
  status?: string;
  temperature?: number | null;
  humidity?: number | null;
  num_devices_sniffed?: number | null;
};
type SensorDetail = {
  sensor: {
    sensor_id: string;
    name?: string;
    lat?: number;
    lon?: number;
    description?: string;
    coordinate_quality?: string;
  };
  timestamp: string;
  latest_values: SensorMetric[];
  history: Record<string, HistoryPoint[]>;
  environment: {
    temperature?: number | null;
    humidity?: number | null;
    num_devices_sniffed?: number | null;
    received_at?: string | null;
  };
};
type LayerVisibility = Record<"buildings" | "roads" | "green" | "transport" | "parking", boolean>;
type MapView = "surface" | "sensors" | "coverage";

const pollutantLabels: Record<string, string> = {
  pm1: "PM1",
  pm10: "PM10",
  pm25: "PM2.5",
  voc_index: "VOC index",
  nox_index: "NOx index",
};

const layerLabels: Array<{ id: keyof LayerVisibility; label: string; icon: ReactNode }> = [
  { id: "buildings", label: "Edifici", icon: <MapIcon size={14} /> },
  { id: "roads", label: "Viabilità", icon: <MapPin size={14} /> },
  { id: "green", label: "Verde", icon: <Trees size={14} /> },
  { id: "transport", label: "Trasporto", icon: <RadioTower size={14} /> },
  { id: "parking", label: "Parcheggi", icon: <Database size={14} /> },
];

const defaultLayers: LayerVisibility = {
  buildings: true,
  roads: true,
  green: true,
  transport: true,
  parking: false,
};

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

function formatTime(value: string | null | undefined) {
  if (!value) return "n/d";
  return new Intl.DateTimeFormat("it-IT", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return "n/d";
  return new Intl.DateTimeFormat("it-IT", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

function formatNumber(value: number | null | undefined, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/d";
  return value.toLocaleString("it-IT", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/d";
  return `${Math.round(value * 100)}%`;
}

function ageLabel(seconds?: number | null) {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return "età n/d";
  if (seconds < 60) return `${seconds}s fa`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min fa`;
  return `${(seconds / 3600).toFixed(1)} h fa`;
}

function statusLabel(status?: string) {
  if (status === "fresh") return "fresco";
  if (status === "recent") return "recente";
  if (status === "aging") return "in ritardo";
  return "n/d";
}

function statusTone(status?: string) {
  if (status === "fresh") return "good";
  if (status === "recent") return "neutral";
  if (status === "aging") return "warn";
  return "muted";
}

function coverageText(active?: number, capable?: number) {
  if (!capable) return `${active ?? 0} sensori`;
  return `${active ?? 0}/${capable} sensori`;
}

function reliabilityLabel(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/d";
  return `${Math.round(value * 100)}%`;
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

function collectPoints(mapData?: MapPayload): LatLon[] {
  const points: LatLon[] = [];
  mapData?.snapshot.forEach((sensor) => points.push(sensor));
  Object.values(mapData?.layers ?? {}).forEach((layer) => collectGeoPoints(layer).forEach((point) => points.push(point)));
  return points;
}

function pathForValues(values: number[]) {
  if (!values.length) return "";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  return values
    .map((value, index) => {
      const x = 4 + (index / Math.max(values.length - 1, 1)) * 92;
      const y = 90 - ((value - min) / span) * 70;
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

function MapFitBounds({ points }: { points: LatLon[] }) {
  const leafletMap = useMap();

  useEffect(() => {
    if (!points.length) return;
    const bounds = points.map((point) => [point.lat, point.lon] as [number, number]);
    leafletMap.fitBounds(bounds, { padding: [32, 32], maxZoom: 17 });
  }, [leafletMap, points]);

  return null;
}

function CampusMap({
  mapData,
  visibility,
  view,
  selectedSensorId,
  onSelectSensor,
}: {
  mapData?: MapPayload;
  visibility: LayerVisibility;
  view: MapView;
  selectedSensorId: string | null;
  onSelectSensor: (sensorId: string) => void;
}) {
  const center: [number, number] = [40.771, 14.79];
  const points = useMemo(() => collectPoints(mapData), [mapData]);
  const grid = view === "coverage" ? mapData?.reliability_grid ?? [] : mapData?.grid ?? [];

  return (
    <div className="map-shell">
      <MapContainer center={center} zoom={15} scrollWheelZoom className="leaflet-map" zoomControl>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <ScaleControl position="bottomleft" />
        <MapFitBounds points={points} />
        {grid.map((cell, index) => (
          <Polygon
            key={`${view}-grid-${index}`}
            positions={cell.polygon.map(([lon, lat]) => [lat, lon])}
            pathOptions={{
              color: "transparent",
              fillColor: rgba(cell.color, view === "coverage" ? 0.52 : 0.42),
              fillOpacity: view === "coverage" ? 0.52 : 0.42,
              weight: 0,
            }}
          />
        ))}
        {visibility.green && mapData?.layers.green ? (
          <GeoJSON
            data={mapData.layers.green as never}
            style={{ color: "#6f8b68", weight: 1, fillColor: "#8fb187", fillOpacity: 0.18, opacity: 0.35 }}
            pointToLayer={(_feature, latlng) => L.circleMarker(latlng, { radius: 3, color: "#7c976f", fillOpacity: 0.85 })}
          />
        ) : null}
        {visibility.buildings && mapData?.layers.buildings ? (
          <GeoJSON
            data={mapData.layers.buildings as never}
            style={{ color: "#536257", weight: 1, fillColor: "#d8ddd4", fillOpacity: 0.28, opacity: 0.35 }}
          />
        ) : null}
        {visibility.roads && mapData?.layers.roads ? (
          <GeoJSON data={mapData.layers.roads as never} style={{ color: "#9c8d74", weight: 2, opacity: 0.55 }} />
        ) : null}
        {visibility.parking && mapData?.layers.parking ? (
          <GeoJSON
            data={mapData.layers.parking as never}
            style={{ color: "#b18858", weight: 1, fillColor: "#d8bb90", fillOpacity: 0.2, opacity: 0.55 }}
          />
        ) : null}
        {visibility.transport && mapData?.layers.transport ? (
          <GeoJSON
            data={mapData.layers.transport as never}
            style={{ color: "#5d7888", weight: 2, fillColor: "#5d7888", fillOpacity: 0.15, opacity: 0.8 }}
            pointToLayer={(_feature, latlng) => L.circleMarker(latlng, { radius: 4, color: "#5d7888", fillOpacity: 0.95 })}
          />
        ) : null}
        {mapData?.snapshot.map((sensor) => {
          const selected = sensor.sensor_id === selectedSensorId;
          const tone = statusTone(sensor.status);
          const fillColor = view === "sensors"
            ? tone === "good"
              ? "#496e4d"
              : tone === "neutral"
                ? "#9a7a46"
                : tone === "warn"
                  ? "#ba6549"
                  : "#5d665e"
            : "#465f45";
          return (
            <CircleMarker
              key={sensor.sensor_id}
              center={[sensor.lat, sensor.lon]}
              radius={selected ? 10 : 7}
              pathOptions={{
                color: selected ? "#f6f2e8" : "#fffaf2",
                fillColor,
                fillOpacity: 0.96,
                weight: selected ? 4 : 3,
              }}
              eventHandlers={{ click: () => onSelectSensor(sensor.sensor_id) }}
            >
              <Popup>
                <strong>{sensor.sensor_name}</strong>
                <br />
                {formatNumber(sensor.estimated_value, 2)} {sensorLabelsSuffix(sensor)}
                <br />
                {statusLabel(sensor.status)} · {ageLabel(sensor.reading_age_seconds)}
              </Popup>
            </CircleMarker>
          );
        })}
      </MapContainer>
    </div>
  );
}

function sensorLabelsSuffix(sensor: SnapshotSensor) {
  return sensor.confidence_label ? `(${sensor.confidence_label})` : "";
}

function SummaryCard({
  title,
  value,
  note,
  icon,
}: {
  title: string;
  value: string;
  note: string;
  icon: ReactNode;
}) {
  return (
    <article className="summary-card">
      <div>
        <span>{title}</span>
        <strong>{value}</strong>
        <small>{note}</small>
      </div>
      <div className="summary-icon">{icon}</div>
    </article>
  );
}

function CoverageBar({ row, selected, onSelect }: { row: CoverageRow; selected: boolean; onSelect: () => void }) {
  return (
    <button className={selected ? "coverage-row active" : "coverage-row"} onClick={onSelect}>
      <div className="coverage-copy">
        <strong>{pollutantLabels[row.pollutant] ?? row.pollutant.toUpperCase()}</strong>
        <span>{coverageText(row.active_sensors, row.capable_sensors)}</span>
      </div>
      <div className="coverage-meter" aria-hidden="true">
        <i style={{ width: `${Math.max(8, Math.round(row.coverage_ratio * 100))}%` }} />
      </div>
      <small>{formatPercent(row.coverage_ratio)}</small>
    </button>
  );
}

function MapLegend({
  view,
  pollutant,
  meta,
}: {
  view: MapView;
  pollutant: string;
  meta?: MapPayload["meta"];
}) {
  if (view === "coverage") {
    return (
      <div className="map-legend-box">
        <strong>Presidio della rete</strong>
        <div className="legend-scale gradient coverage" />
        <div className="legend-axis">
          <span>basso</span>
          <span>alto</span>
        </div>
      </div>
    );
  }

  if (view === "surface") {
    return (
      <div className="map-legend-box">
        <strong>{pollutantLabels[pollutant] ?? pollutant.toUpperCase()}</strong>
        <div className="legend-scale gradient quality" />
        <div className="legend-axis">
          <span>{formatNumber(meta?.min_value ?? null, 1)}</span>
          <span>{formatNumber(meta?.max_value ?? null, 1)}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="map-legend-box">
      <strong>Freschezza marker</strong>
      <div className="status-legend compact">
        <span className="legend-item">
          <i className="legend-dot good" />
          fresco
        </span>
        <span className="legend-item">
          <i className="legend-dot neutral" />
          recente
        </span>
        <span className="legend-item">
          <i className="legend-dot warn" />
          in ritardo
        </span>
      </div>
    </div>
  );
}

function TrendChart({ points, pollutant }: { points: HistoryPoint[]; pollutant: string }) {
  if (!points.length) {
    return <div className="chart-empty">Storico non disponibile per {pollutantLabels[pollutant] ?? pollutant.toUpperCase()}.</div>;
  }
  const values = points.map((point) => point.estimated_value);
  return (
    <div className="chart-shell">
      <svg viewBox="0 0 100 100" className="trend-chart" role="img" aria-label={`Storico ${pollutant}`}>
        <path d={pathForValues(values)} className="trend-line" />
      </svg>
      <div className="chart-axis">
        <span>{formatTime(points[0]?.timestamp)}</span>
        <span>{formatTime(points.at(-1)?.timestamp)}</span>
      </div>
    </div>
  );
}

function App() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [timestamps, setTimestamps] = useState<string[]>([]);
  const [pollutant, setPollutant] = useState("pm10");
  const [timestamp, setTimestamp] = useState<string | null>(null);
  const [mapData, setMapData] = useState<MapPayload>();
  const [sensorDetail, setSensorDetail] = useState<SensorDetail | null>(null);
  const [selectedSensorId, setSelectedSensorId] = useState<string | null>(null);
  const [layerVisibility, setLayerVisibility] = useState<LayerVisibility>(defaultLayers);
  const [mapView, setMapView] = useState<MapView>("surface");
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);
  const [isPending, startTransition] = useTransition();
  const deferredSearch = useDeferredValue(search);

  useEffect(() => {
    startTransition(() => {
      getJson<{ status: string }>("/api/refresh", { method: "POST" })
        .catch(() => undefined)
        .then(() => getJson<Summary>("/api/summary"))
        .then((payload) => {
          setSummary(payload);
          setPollutant((current) => current || payload.default_pollutant);
          setTimestamp(payload.latest_timestamp);
          setError(null);
        })
        .catch((reason) => setError(reason.message));
    });
  }, [refreshTick]);

  useEffect(() => {
    const timer = window.setInterval(() => setRefreshTick((current) => current + 1), 60000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!pollutant) return;
    getJson<{ timestamps: string[] }>(`/api/timestamps?pollutant=${encodeURIComponent(pollutant)}`)
      .then((payload) => {
        setTimestamps(payload.timestamps);
        setTimestamp((current) => (current && payload.timestamps.includes(current) ? current : payload.timestamps.at(-1) ?? null));
      })
      .catch((reason) => setError(reason.message));
  }, [pollutant, refreshTick]);

  useEffect(() => {
    if (!pollutant || !timestamp) return;
    startTransition(() => {
      getJson<MapPayload>(`/api/map?pollutant=${encodeURIComponent(pollutant)}&timestamp=${encodeURIComponent(timestamp)}`)
        .then((payload) => {
          setMapData(payload);
          setError(null);
        })
        .catch((reason) => setError(reason.message));
    });
  }, [pollutant, timestamp, refreshTick]);

  useEffect(() => {
    if (!mapData?.snapshot.length) {
      setSelectedSensorId(null);
      return;
    }
    const stillAvailable = selectedSensorId && mapData.snapshot.some((sensor) => sensor.sensor_id === selectedSensorId);
    if (stillAvailable) return;
    const candidate = [...mapData.snapshot].sort((a, b) => (a.reading_age_seconds ?? 999999) - (b.reading_age_seconds ?? 999999))[0];
    setSelectedSensorId(candidate?.sensor_id ?? null);
  }, [mapData, selectedSensorId]);

  useEffect(() => {
    if (!selectedSensorId || !timestamp) return;
    getJson<SensorDetail>(
      `/api/sensor-detail?sensor_id=${encodeURIComponent(selectedSensorId)}&timestamp=${encodeURIComponent(timestamp)}`,
    )
      .then((payload) => {
        setSensorDetail(payload);
        setError(null);
      })
      .catch((reason) => setError(reason.message));
  }, [selectedSensorId, timestamp]);

  const activeSnapshot = mapData?.snapshot ?? [];
  const filteredSnapshot = useMemo(() => {
    const query = deferredSearch.trim().toLowerCase();
    const sorted = [...activeSnapshot].sort((a, b) => {
      const age = (a.reading_age_seconds ?? Number.MAX_SAFE_INTEGER) - (b.reading_age_seconds ?? Number.MAX_SAFE_INTEGER);
      if (age !== 0) return age;
      return (b.estimated_value ?? 0) - (a.estimated_value ?? 0);
    });
    if (!query) return sorted;
    return sorted.filter((sensor) => sensor.sensor_name.toLowerCase().includes(query) || sensor.sensor_id.toLowerCase().includes(query));
  }, [activeSnapshot, deferredSearch]);

  const selectedSensorRow = useMemo(
    () => activeSnapshot.find((sensor) => sensor.sensor_id === selectedSensorId) ?? null,
    [activeSnapshot, selectedSensorId],
  );

  const currentHistory = useMemo(() => {
    if (!sensorDetail) return [];
    return sensorDetail.history[pollutant] ?? [];
  }, [pollutant, sensorDetail]);

  const currentMetric = useMemo(() => {
    if (!sensorDetail) return null;
    return sensorDetail.latest_values.find((item) => item.pollutant === pollutant) ?? sensorDetail.latest_values[0] ?? null;
  }, [pollutant, sensorDetail]);

  const selectedCoverage = useMemo(() => {
    return summary?.coverage_by_pollutant.find((item) => item.pollutant === pollutant) ?? null;
  }, [pollutant, summary]);

  const layerCountSummary = summary?.layer_counts ?? {};
  const dashboardReady = Boolean(summary && mapData);

  return (
    <main className="app-shell" data-testid="air-twin-cockpit">
      <aside className="left-rail">
        <div className="brand-block">
          <div className="brand-mark">
            <Leaf size={18} />
          </div>
          <div>
            <strong>UNISA</strong>
            <span>Air Quality Digital Twin</span>
          </div>
        </div>

        <nav className="rail-nav" aria-label="Sezioni dashboard">
          <a href="#monitor">Monitor</a>
          <a href="#sensors">Sensori</a>
          <a href="#history">Storico</a>
          <a href="#provenance">Dati</a>
        </nav>

        <div className="rail-card">
          <span>Panoramica</span>
          <strong>Monitoraggio campus</strong>
          <p>Copertura sensori, qualità dell'aria, dettaglio puntuale e storico operativo.</p>
        </div>

        <div className="rail-card">
          <span>Snapshot operativo</span>
          <strong>{summary ? formatDateTime(timestamp) : "Caricamento..."}</strong>
          <p>
            {summary
              ? `Bucket ${summary.ingestion?.snapshot_bucket_minutes ?? "n/d"} min · finestra freschezza ${
                  summary.ingestion?.snapshot_freshness_minutes ?? "n/d"
                } min`
              : "Allineamento dati sensori in corso"}
          </p>
        </div>

        <button className="refresh-button" onClick={() => setRefreshTick((current) => current + 1)}>
          <RefreshCcw size={16} />
          Aggiorna dati
        </button>
      </aside>

      <section className="workspace">
        <header className="hero" id="monitor">
          <div className="hero-copy">
            <h1>Cabina operativa sensori UNISA</h1>
            <p>Monitora il campus con snapshot aggiornati, superficie di qualità dell'aria, dettaglio sensore e storico recente.</p>
          </div>
          <div className="hero-meta">
            <span>{summary?.source ?? "UNISA AQDT"}</span>
            <span>{summary ? formatTime(summary.latest_received_at) : "Aggiornamento..."}</span>
            <span>{summary?.campus.name ?? "Campus Fisciano"}</span>
          </div>
        </header>

        {dashboardReady ? (
          <>
        <section className="summary-grid">
          <SummaryCard
            title="Sensori attivi"
            value={coverageText(summary?.active_sensors, summary?.capable_sensors)}
            note="Nello snapshot selezionato"
            icon={<RadioTower size={20} />}
          />
          <SummaryCard
            title="Copertura"
            value={formatPercent(summary?.coverage_ratio)}
            note={selectedCoverage ? `${pollutantLabels[selectedCoverage.pollutant] ?? selectedCoverage.pollutant} attivo` : "Copertura snapshot"}
            icon={<Gauge size={20} />}
          />
          <SummaryCard
            title="Ultima ricezione"
            value={formatTime(summary?.latest_received_at)}
            note="Tempo di arrivo più recente"
            icon={<Clock3 size={20} />}
          />
          <SummaryCard
            title="Osservazioni disponibili"
            value={formatNumber(summary?.raw_rows, 0)}
            note="Letture archiviate nella serie"
            icon={<Archive size={20} />}
          />
        </section>

        {error ? <div className="error-banner">{error}</div> : null}

        <section className="operations-grid">
          <article className="panel coverage-panel">
            <div className="panel-head">
              <div>
                <span>Monitoraggio</span>
                <h2>Copertura per inquinante</h2>
              </div>
              {isPending ? <small>Aggiornamento in corso</small> : null}
            </div>
            <div className="coverage-list">
              {(summary?.coverage_by_pollutant ?? []).map((row) => (
                <CoverageBar
                  key={row.pollutant}
                  row={row}
                  selected={row.pollutant === pollutant}
                  onSelect={() => setPollutant(row.pollutant)}
                />
              ))}
            </div>
            <div className="controls-bar">
              <label>
                <span>Inquinante</span>
                <select value={pollutant} onChange={(event) => setPollutant(event.target.value)}>
                  {summary?.pollutants.map((item) => (
                    <option key={item} value={item}>
                      {pollutantLabels[item] ?? item.toUpperCase()}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Timestamp operativo</span>
                <select value={timestamp ?? ""} onChange={(event) => setTimestamp(event.target.value)}>
                  {timestamps.map((item) => (
                    <option key={item} value={item}>
                      {formatDateTime(item)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="status-legend">
              <span className="legend-item">
                <i className="legend-dot good" />
                fresco
              </span>
              <span className="legend-item">
                <i className="legend-dot neutral" />
                recente
              </span>
              <span className="legend-item">
                <i className="legend-dot warn" />
                in ritardo
              </span>
            </div>
          </article>

          <article className="panel map-panel">
            <div className="panel-head">
              <div>
                <span>Mappa campus</span>
                <h2>Qualità dell'aria {pollutantLabels[pollutant] ?? pollutant.toUpperCase()}</h2>
              </div>
              <small>
                {coverageText(mapData?.meta?.active_sensors, mapData?.meta?.capable_sensors)} · mediana età{" "}
                {ageLabel(mapData?.meta?.median_age_seconds)}
              </small>
            </div>
            <div className="map-toolbar">
              <div className="view-switch" aria-label="Vista mappa">
                <button className={mapView === "surface" ? "active" : ""} onClick={() => setMapView("surface")}>
                  Superficie
                </button>
                <button className={mapView === "sensors" ? "active" : ""} onClick={() => setMapView("sensors")}>
                  Sensori
                </button>
                <button className={mapView === "coverage" ? "active" : ""} onClick={() => setMapView("coverage")}>
                  Copertura
                </button>
              </div>
              <MapLegend view={mapView} pollutant={pollutant} meta={mapData?.meta} />
            </div>
            <div className="layer-switches">
              {layerLabels.map((layer) => (
                <button
                  key={layer.id}
                  className={layerVisibility[layer.id] ? "layer-chip active" : "layer-chip"}
                  onClick={() => setLayerVisibility((current) => ({ ...current, [layer.id]: !current[layer.id] }))}
                >
                  {layer.icon}
                  {layer.label}
                </button>
              ))}
            </div>
            <CampusMap
              mapData={mapData}
              visibility={layerVisibility}
              view={mapView}
              selectedSensorId={selectedSensorId}
              onSelectSensor={setSelectedSensorId}
            />
            <div className="map-caption">
              <p>
                {mapView === "surface"
                  ? "La superficie mostra la distribuzione stimata nel campus a partire dalle misure disponibili nello snapshot selezionato."
                  : mapView === "coverage"
                    ? "La vista copertura evidenzia le aree meglio presidiate dalla rete sensori disponibile in questo momento."
                    : "La vista sensori mette al centro i marker e la freschezza delle misure acquisite."}{" "}
                I layer di contesto sono basati su edifici, strade, verde, trasporto e parcheggi del campus.
              </p>
            </div>
          </article>
        </section>

        <section className="detail-grid">
          <article className="panel sensor-panel">
            <div className="panel-head">
              <div>
                <span>Sensore selezionato</span>
                <h2>{sensorDetail?.sensor.name ?? selectedSensorRow?.sensor_name ?? "Seleziona un sensore"}</h2>
              </div>
              <small>{selectedSensorId ?? "n/d"}</small>
            </div>

            <div className="sensor-meta">
              <div>
                <MapPin size={14} />
                <span>
                  {formatNumber(sensorDetail?.sensor.lat, 5)}, {formatNumber(sensorDetail?.sensor.lon, 5)}
                </span>
              </div>
              <div>
                <Clock3 size={14} />
                <span>{ageLabel(currentMetric?.reading_age_seconds)}</span>
              </div>
              <div>
                <Activity size={14} />
                <span>{statusLabel(currentMetric?.status)}</span>
              </div>
            </div>

            <div className="metric-grid">
              {(sensorDetail?.latest_values ?? []).map((metric) => (
                <div key={metric.pollutant} className="metric-card">
                  <span>{pollutantLabels[metric.pollutant] ?? metric.pollutant.toUpperCase()}</span>
                  <strong>{formatNumber(metric.estimated_value, 2)}</strong>
                  <small>{ageLabel(metric.reading_age_seconds)}</small>
                </div>
              ))}
            </div>

            <div className="environment-grid">
              <div>
                <Thermometer size={16} />
                <div>
                  <span>Temperatura</span>
                  <strong>{formatNumber(sensorDetail?.environment.temperature, 1)} °C</strong>
                </div>
              </div>
              <div>
                <Droplets size={16} />
                <div>
                  <span>Umidità</span>
                  <strong>{formatNumber(sensorDetail?.environment.humidity, 0)}%</strong>
                </div>
              </div>
              <div>
                <RadioTower size={16} />
                <div>
                  <span>Device sniffed</span>
                  <strong>{formatNumber(sensorDetail?.environment.num_devices_sniffed, 0)}</strong>
                </div>
              </div>
            </div>
          </article>

          <article className="panel history-panel" id="history">
            <div className="panel-head">
              <div>
                <span>Storico sensore</span>
                <h2>{pollutantLabels[pollutant] ?? pollutant.toUpperCase()}</h2>
              </div>
              <small>{sensorDetail?.sensor.name ?? "Seleziona un sensore dalla mappa o dalla tabella"}</small>
            </div>
            <TrendChart points={currentHistory} pollutant={pollutant} />
            <div className="history-footer">
              <div>
                <span>Ultima misura</span>
                <strong>{formatDateTime(currentMetric?.measured_at ?? null)}</strong>
              </div>
              <div>
                <span>Ultima ricezione</span>
                <strong>{formatDateTime(sensorDetail?.environment.received_at ?? null)}</strong>
              </div>
            </div>
          </article>
        </section>

        <section className="panel table-panel" id="sensors">
          <div className="panel-head">
            <div>
              <span>Registro sensori</span>
              <h2>Snapshot operativo corrente</h2>
            </div>
            <label className="search-field">
              <Search size={14} />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Cerca per nome o ID sensore"
              />
            </label>
          </div>

          <div className="sensor-table">
            <div className="sensor-table-head">
              <span>Sensore</span>
              <span>Stato</span>
              <span>Valore</span>
              <span>Età dato</span>
              <span>Misurato</span>
            </div>
            {filteredSnapshot.map((sensor) => (
              <button
                key={sensor.sensor_id}
                className={sensor.sensor_id === selectedSensorId ? "sensor-row active" : "sensor-row"}
                onClick={() => setSelectedSensorId(sensor.sensor_id)}
              >
                <span>
                  <strong>{sensor.sensor_name}</strong>
                  <small>{sensor.sensor_id}</small>
                </span>
                <span className={`status-pill ${statusTone(sensor.status)}`}>{statusLabel(sensor.status)}</span>
                <span>{formatNumber(sensor.estimated_value, 2)}</span>
                <span>{ageLabel(sensor.reading_age_seconds)}</span>
                <span>{formatTime(sensor.measured_at ?? null)}</span>
              </button>
            ))}
          </div>
        </section>

        <section className="provenance-grid" id="provenance">
          <article className="panel provenance-panel">
            <div className="panel-head">
              <div>
                <span>Dati</span>
                <h2>Rete e cartografia campus</h2>
              </div>
            </div>
            <ul className="provenance-list">
              <li>Snapshot operativo costruito sulle misure più recenti disponibili per ciascun sensore.</li>
              <li>La superficie mappa sintetizza l'andamento del campus a partire dallo snapshot selezionato.</li>
              <li>Il dettaglio sensore e lo storico mostrano le ultime letture archiviate per quel punto.</li>
              <li>Layer di contesto campus da OpenStreetMap: {Object.entries(layerCountSummary).map(([key, value]) => `${key} ${value}`).join(" · ")}.</li>
            </ul>
          </article>

          <article className="panel provenance-panel">
            <div className="panel-head">
              <div>
                <span>Dataset</span>
                <h2>Stato ingestione</h2>
              </div>
            </div>
            <div className="dataset-grid">
              <div>
                <span>Sensori registrati</span>
                <strong>{summary?.sensors ?? "n/d"}</strong>
              </div>
              <div>
                <span>Snapshot operativi</span>
                <strong>{formatNumber(summary?.snapshot_rows, 0)}</strong>
              </div>
              <div>
                <span>Osservazioni archiviate</span>
                <strong>{formatNumber(summary?.raw_rows, 0)}</strong>
              </div>
              <div>
                <span>Ultima generazione</span>
                <strong>{formatTime(summary?.ingestion?.generated_at ?? null)}</strong>
              </div>
            </div>
          </article>
        </section>
          </>
        ) : (
          <section className="panel loading-panel" aria-live="polite">
            <div className="panel-head">
              <div>
                <span>{error ? "Errore" : "Caricamento"}</span>
                <h2>{error ? "Dashboard non disponibile" : "Allineamento dashboard"}</h2>
              </div>
            </div>
            {error ? (
              <p>
                {error}. Verifica che l'API sia attiva con <code>make api</code> e che il frontend sia avviato con <code>make web</code>.
              </p>
            ) : (
              <p>I dati del campus sono in aggiornamento. La dashboard viene popolata non appena snapshot e mappa sono pronti.</p>
            )}
          </section>
        )}
      </section>
    </main>
  );
}

export default App;
