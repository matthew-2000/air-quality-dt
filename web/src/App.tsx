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
import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { CircleMarker, GeoJSON, MapContainer, Polygon, Popup, ScaleControl, TileLayer, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { getJson, openEventStream, requestMessage } from "./api";
import {
  ageLabel,
  coverageText,
  formatDateTime,
  formatNumber,
  formatPercent,
  formatTime,
  pathForValues,
  pollutantLabels,
  pollutantUnits,
  statusLabel,
  statusTone,
} from "./format";
import { CoverageBar } from "./components/CoverageBar";
import { DataJobsPanel } from "./components/DataJobsPanel";
import { EmptyStatePanel } from "./components/EmptyStatePanel";
import { SummaryCard } from "./components/SummaryCard";
import { TwinAnalyticsPanel } from "./components/TwinAnalyticsPanel";
import { ProductWorkflowPanels } from "./components/ProductWorkflowPanels";
import type {
  AnalyticsPayload,
  FeatureCollection,
  HistoryPoint,
  LatLon,
  LayerVisibility,
  LiveStreamEvent,
  MapPayload,
  MapView,
  SensorDetail,
  SnapshotSensor,
  StreamStatus,
  Summary,
} from "./types";

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

function rgba(color: [number, number, number, number], alphaScale = 1) {
  return `rgba(${color[0]}, ${color[1]}, ${color[2]}, ${(color[3] / 255) * alphaScale})`;
}

function liveFeedMessage(summary?: Summary | null) {
  const feed = summary?.live_feed;
  if (!feed) return null;
  if (feed.status === "unconfigured") {
    const missing = (feed.missing_env ?? []).join(", ");
    return `Feed MQTT non configurato${missing ? `: mancano ${missing}.` : "."}`;
  }
  if (feed.status === "stale") {
    const age = feed.age_minutes ?? null;
    return age === null
      ? "Feed MQTT fermo: l'ultima misura disponibile non è recente."
      : `Feed MQTT fermo: ultima misura ricevuta ${age} minuti fa.`;
  }
  return null;
}

function streamStatusLabel(status: StreamStatus) {
  if (status === "live") return "stream SSE attivo";
  if (status === "retrying") return "riconnessione stream";
  if (status === "unsupported") return "fallback polling";
  return "connessione stream";
}

function parseLiveStreamEvent(event: MessageEvent<string>): LiveStreamEvent | null {
  try {
    return JSON.parse(event.data) as LiveStreamEvent;
  } catch {
    return null;
  }
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
      <MapContainer center={center} zoom={15} scrollWheelZoom={false} className="leaflet-map" zoomControl>
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
  const min = Math.min(...values);
  const max = Math.max(...values);
  const latest = values.at(-1);
  const unit = pollutantUnits[pollutant] ?? "";
  const coordinates = values.map((value, index) => {
    const span = max - min || 1;
    return {
      x: 7 + (index / Math.max(values.length - 1, 1)) * 86,
      y: 84 - ((value - min) / span) * 62,
      value,
      timestamp: points[index]?.timestamp,
    };
  });
  return (
    <div className="chart-shell">
      <div className="chart-summary">
        <div>
          <span>Ultimo valore</span>
          <strong>
            {formatNumber(latest, 2)} {unit}
          </strong>
        </div>
        <div>
          <span>Intervallo</span>
          <strong>
            {formatNumber(min, 2)} - {formatNumber(max, 2)}
          </strong>
        </div>
      </div>
      <svg
        viewBox="0 0 100 100"
        className="trend-chart"
        role="img"
        aria-label={`Storico ${pollutantLabels[pollutant] ?? pollutant.toUpperCase()}, minimo ${formatNumber(min, 2)}, massimo ${formatNumber(max, 2)}`}
      >
        <line x1="7" y1="22" x2="93" y2="22" className="chart-grid-line" />
        <line x1="7" y1="53" x2="93" y2="53" className="chart-grid-line" />
        <line x1="7" y1="84" x2="93" y2="84" className="chart-grid-line" />
        <path d={pathForValues(values)} className="trend-line" />
        {coordinates.map((point, index) => (
          <circle key={`${point.timestamp}-${index}`} cx={point.x} cy={point.y} r={index === coordinates.length - 1 ? 2.2 : 1.4} className="trend-point">
            <title>
              {formatTime(point.timestamp)}: {formatNumber(point.value, 2)} {unit}
            </title>
          </circle>
        ))}
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
  const [analytics, setAnalytics] = useState<AnalyticsPayload>();
  const [sensorDetail, setSensorDetail] = useState<SensorDetail | null>(null);
  const [selectedSensorId, setSelectedSensorId] = useState<string | null>(null);
  const [layerVisibility, setLayerVisibility] = useState<LayerVisibility>(defaultLayers);
  const [mapView, setMapView] = useState<MapView>("surface");
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);
  const [isSummaryLoading, setSummaryLoading] = useState(true);
  const [isMapLoading, setMapLoading] = useState(false);
  const [isAnalyticsLoading, setAnalyticsLoading] = useState(false);
  const [isSensorLoading, setSensorLoading] = useState(false);
  const [isRefreshing, setRefreshing] = useState(false);
  const [lastLoadedAt, setLastLoadedAt] = useState<Date | null>(null);
  const [streamStatus, setStreamStatus] = useState<StreamStatus>("connecting");
  const deferredSearch = useDeferredValue(search);
  const liveFingerprintRef = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setSummaryLoading(true);
    getJson<Summary>("/api/summary")
      .then((payload) => {
        if (cancelled) return;
        setSummary(payload);
        setPollutant((current) => current || payload.default_pollutant);
        setTimestamp(payload.latest_timestamp);
        setLastLoadedAt(new Date());
        setError(null);
      })
      .catch((reason) => {
        if (!cancelled) setError(requestMessage(reason));
      })
      .finally(() => {
        if (!cancelled) setSummaryLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshTick]);

  useEffect(() => {
    if (typeof window === "undefined") {
      setStreamStatus("unsupported");
      return undefined;
    }

    if (!("EventSource" in window)) {
      setStreamStatus("unsupported");
      const timer = globalThis.setInterval(() => setRefreshTick((current) => current + 1), 60000);
      return () => globalThis.clearInterval(timer);
    }

    setStreamStatus("connecting");
    const stream = openEventStream("/api/stream");
    const handleConnected = (event: Event) => {
      const payload = parseLiveStreamEvent(event as MessageEvent<string>);
      if (!payload) return;
      liveFingerprintRef.current = payload.fingerprint;
      setStreamStatus("live");
      setError(null);
    };
    const handleSnapshotUpdate = (event: Event) => {
      const payload = parseLiveStreamEvent(event as MessageEvent<string>);
      if (!payload) return;
      setStreamStatus("live");
      if (payload.fingerprint === liveFingerprintRef.current) return;
      liveFingerprintRef.current = payload.fingerprint;
      setRefreshTick((current) => current + 1);
    };
    const handleStreamError = () => {
      setStreamStatus("retrying");
    };

    stream.addEventListener("connected", handleConnected);
    stream.addEventListener("snapshot_update", handleSnapshotUpdate);
    stream.addEventListener("stream_error", handleStreamError);
    stream.onerror = () => {
      setStreamStatus("retrying");
    };

    return () => {
      stream.removeEventListener("connected", handleConnected);
      stream.removeEventListener("snapshot_update", handleSnapshotUpdate);
      stream.removeEventListener("stream_error", handleStreamError);
      stream.close();
    };
  }, []);

  useEffect(() => {
    if (!pollutant) return;
    let cancelled = false;
    getJson<{ timestamps: string[] }>(`/api/timestamps?pollutant=${encodeURIComponent(pollutant)}`)
      .then((payload) => {
        if (cancelled) return;
        setTimestamps(payload.timestamps);
        setTimestamp((current) => (current && payload.timestamps.includes(current) ? current : payload.timestamps.at(-1) ?? null));
      })
      .catch((reason) => {
        if (!cancelled) setError(requestMessage(reason));
      });
    return () => {
      cancelled = true;
    };
  }, [pollutant, refreshTick]);

  useEffect(() => {
    if (!pollutant || !timestamp) return;
    let cancelled = false;
    setMapLoading(true);
    getJson<MapPayload>(`/api/map?pollutant=${encodeURIComponent(pollutant)}&timestamp=${encodeURIComponent(timestamp)}`)
      .then((payload) => {
        if (cancelled) return;
        setMapData(payload);
        setLastLoadedAt(new Date());
        setError(null);
      })
      .catch((reason) => {
        if (!cancelled) setError(requestMessage(reason));
      })
      .finally(() => {
        if (!cancelled) setMapLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [pollutant, timestamp, refreshTick]);

  useEffect(() => {
    if (!pollutant) return;
    let cancelled = false;
    const timestampQuery = timestamp ? `&timestamp=${encodeURIComponent(timestamp)}` : "";
    setAnalyticsLoading(true);
    getJson<AnalyticsPayload>(`/api/analytics?pollutant=${encodeURIComponent(pollutant)}${timestampQuery}`)
      .then((payload) => {
        if (cancelled) return;
        setAnalytics(payload);
        setError(null);
      })
      .catch((reason) => {
        if (!cancelled) setError(requestMessage(reason));
      })
      .finally(() => {
        if (!cancelled) setAnalyticsLoading(false);
      });
    return () => {
      cancelled = true;
    };
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
    let cancelled = false;
    setSensorLoading(true);
    getJson<SensorDetail>(
      `/api/sensor-detail?sensor_id=${encodeURIComponent(selectedSensorId)}&timestamp=${encodeURIComponent(timestamp)}`,
    )
      .then((payload) => {
        if (cancelled) return;
        setSensorDetail(payload);
        setError(null);
      })
      .catch((reason) => {
        if (!cancelled) setError(requestMessage(reason));
      })
      .finally(() => {
        if (!cancelled) setSensorLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedSensorId, timestamp]);

  const handleManualRefresh = () => {
    setRefreshing(true);
    getJson<{ status: string }>("/api/refresh", { method: "POST" })
      .then(() => {
        setRefreshTick((current) => current + 1);
        setError(null);
      })
      .catch((reason) => setError(requestMessage(reason)))
      .finally(() => setRefreshing(false));
  };

  const handleDataChanged = () => {
    setRefreshTick((current) => current + 1);
  };

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
  const observationRows = summary?.observation_rows ?? summary?.raw_rows;
  const rawMessageRows = summary?.raw_message_rows ?? summary?.ingestion?.raw_message_rows;
  const hasObservations = Boolean(summary?.latest_timestamp && summary.pollutants.length && summary.rows > 0);
  const dashboardReady = Boolean(summary && (mapData || !hasObservations));
  const isLoading = isSummaryLoading || isMapLoading || isAnalyticsLoading || isSensorLoading || isRefreshing;
  const loadingTitle = error ? "Dashboard non disponibile" : "Allineamento dashboard";
  const loadingCopy = isSummaryLoading
    ? "Lettura dello stato API e dello snapshot più recente."
    : isMapLoading
      ? "Costruzione della mappa e dei layer campus."
      : "Preparazione del dettaglio sensore.";
  const liveWarning = liveFeedMessage(summary);

  return (
    <main className="app-shell" data-testid="air-twin-cockpit" aria-busy={isLoading}>
      <aside className="left-rail">
        <div className="rail-top">
          <div className="brand-block">
            <div className="brand-mark">
              <Leaf size={18} />
            </div>
            <div>
              <strong>UNISA</strong>
              <span>Air Quality Digital Twin</span>
            </div>
          </div>

          <button className="refresh-button" onClick={handleManualRefresh} disabled={isRefreshing || isSummaryLoading}>
            <RefreshCcw size={16} className={isRefreshing ? "spin-icon" : ""} />
            {isRefreshing ? "Aggiornamento" : "Aggiorna dati"}
          </button>
        </div>

        <nav className="rail-nav" aria-label="Sezioni dashboard">
          <a href="#monitor">Overview</a>
          <a href="#map">Map</a>
          <a href="#scenarios">Scenari</a>
          <a href="#sensors">Sensor Explorer</a>
          <a href="#insights">Insights</a>
          <a href="#data-center">Data Center</a>
          <a href="#settings">Settings</a>
        </nav>

        <div className="rail-meta-grid">
          <div className="rail-card rail-card-overview">
            <span>Panoramica</span>
            <strong>Monitoraggio campus</strong>
            <p>Copertura sensori, qualità dell'aria, dettaglio puntuale e storico operativo.</p>
          </div>

          <div className="rail-card rail-card-status">
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
        </div>
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
            <span>{streamStatusLabel(streamStatus)}</span>
            {lastLoadedAt ? <span>UI {formatTime(lastLoadedAt.toISOString())}</span> : null}
          </div>
        </header>

        {dashboardReady ? (
          <>
        {isLoading ? (
          <div className="sync-banner" role="status">
            <RefreshCcw size={15} className="spin-icon" />
            {isRefreshing ? "Refresh forzato dei dataset in corso" : "Aggiornamento vista in corso"}
          </div>
        ) : null}

        {liveWarning ? <div className="error-banner" role="alert">{liveWarning}</div> : null}

        {!hasObservations && summary ? (
          <>
            <EmptyStatePanel summary={summary} observationRows={observationRows} />
            <ProductWorkflowPanels pollutant={pollutant} timestamp={timestamp} summary={summary} />
            <section className="provenance-grid" id="provenance">
              <DataJobsPanel onDataChanged={handleDataChanged} />
            </section>
          </>
        ) : (
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
            note={
              summary?.live_feed?.status === "live"
                ? "Tempo di arrivo più recente"
                : summary?.live_feed?.status === "unconfigured"
                  ? "Broker MQTT non configurato"
                  : "Feed non aggiornato"
            }
            icon={<Clock3 size={20} />}
          />
          <SummaryCard
            title="Osservazioni disponibili"
            value={formatNumber(observationRows, 0)}
            note="Letture archiviate nella serie"
            icon={<Archive size={20} />}
          />
        </section>

        {error ? <div className="error-banner" role="alert">{error}</div> : null}

        <section className="operations-grid">
          <article className="panel coverage-panel">
            <div className="panel-head">
              <div>
                <span>Monitoraggio</span>
                <h2>Copertura per inquinante</h2>
              </div>
              {isLoading ? <small>Aggiornamento in corso</small> : null}
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

          <article className="panel map-panel" id="map">
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
              <div className="view-switch" role="tablist" aria-label="Vista mappa">
                <button
                  type="button"
                  role="tab"
                  aria-selected={mapView === "surface"}
                  className={mapView === "surface" ? "active" : ""}
                  onClick={() => setMapView("surface")}
                >
                  Superficie
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={mapView === "sensors"}
                  className={mapView === "sensors" ? "active" : ""}
                  onClick={() => setMapView("sensors")}
                >
                  Sensori
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={mapView === "coverage"}
                  className={mapView === "coverage" ? "active" : ""}
                  onClick={() => setMapView("coverage")}
                >
                  Copertura
                </button>
              </div>
              <MapLegend view={mapView} pollutant={pollutant} meta={mapData?.meta} />
            </div>
            <div className="layer-switches">
              {layerLabels.map((layer) => (
                <button
                  key={layer.id}
                  type="button"
                  aria-pressed={layerVisibility[layer.id]}
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
              <small>{isSensorLoading ? "Aggiornamento dettaglio" : selectedSensorId ?? "n/d"}</small>
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
              <div>
                <Gauge size={16} />
                <div>
                  <span>Vento 10m</span>
                  <strong>{formatNumber(sensorDetail?.environment.wind_speed_10m, 1)} km/h</strong>
                </div>
              </div>
              <div>
                <Trees size={16} />
                <div>
                  <span>Indice verde</span>
                  <strong>{formatNumber(sensorDetail?.environment.green_index, 2)}</strong>
                </div>
              </div>
              <div>
                <Archive size={16} />
                <div>
                  <span>Background</span>
                  <strong>{formatNumber(sensorDetail?.environment.background_value, 1)}</strong>
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

        <TwinAnalyticsPanel analytics={analytics} />

        <ProductWorkflowPanels pollutant={pollutant} timestamp={timestamp} summary={summary} />

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
                aria-label="Cerca sensore"
              />
            </label>
          </div>

          <table className="sensor-table">
            <thead>
              <tr>
                <th scope="col">Sensore</th>
                <th scope="col">Stato</th>
                <th scope="col">Valore</th>
                <th scope="col">Età dato</th>
                <th scope="col">Misurato</th>
              </tr>
            </thead>
            <tbody>
              {filteredSnapshot.map((sensor) => {
                const selected = sensor.sensor_id === selectedSensorId;
                return (
                  <tr
                    key={sensor.sensor_id}
                    className={selected ? "sensor-row active" : "sensor-row"}
                    onClick={() => setSelectedSensorId(sensor.sensor_id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        setSelectedSensorId(sensor.sensor_id);
                      }
                    }}
                    tabIndex={0}
                    aria-selected={selected}
                  >
                    <th scope="row">
                      <strong>{sensor.sensor_name}</strong>
                      <small>{sensor.sensor_id}</small>
                    </th>
                    <td>
                      <span className={`status-pill ${statusTone(sensor.status)}`}>{statusLabel(sensor.status)}</span>
                    </td>
                    <td>{formatNumber(sensor.estimated_value, 2)}</td>
                    <td>{ageLabel(sensor.reading_age_seconds)}</td>
                    <td>{formatTime(sensor.measured_at ?? null)}</td>
                  </tr>
                );
              })}
              {!filteredSnapshot.length ? (
                <tr className="sensor-empty">
                  <td colSpan={5}>Nessun sensore corrisponde alla ricerca.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
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

          <DataJobsPanel onDataChanged={handleDataChanged} />

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
                <strong>{formatNumber(observationRows, 0)}</strong>
              </div>
              <div>
                <span>Messaggi MQTT raw</span>
                <strong>{formatNumber(rawMessageRows, 0)}</strong>
              </div>
              <div>
                <span>Ultima generazione</span>
                <strong>{formatTime(summary?.ingestion?.generated_at ?? null)}</strong>
              </div>
              <div>
                <span>Stato feed live</span>
                <strong>
                  {summary?.live_feed?.status === "live"
                    ? "attivo"
                    : summary?.live_feed?.status === "stale"
                      ? "stale"
                      : summary?.live_feed?.status === "unconfigured"
                        ? "non configurato"
                        : "n/d"}
                </strong>
              </div>
            </div>
          </article>
        </section>
          </>
        )}
          </>
        ) : (
          <section className="panel loading-panel" aria-live="polite">
            <div className="panel-head">
              <div>
                <span>{error ? "Errore" : "Caricamento"}</span>
                <h2>{loadingTitle}</h2>
              </div>
            </div>
            <div className="loading-track" aria-hidden="true">
              <i />
            </div>
            {error ? (
              <p>{error}. Riprova l'aggiornamento dalla dashboard oppure passa in modalità demo con dati simulati.</p>
            ) : (
              <p>{loadingCopy}</p>
            )}
          </section>
        )}
      </section>
    </main>
  );
}

export default App;
