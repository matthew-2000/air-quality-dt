import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  CheckCircle2,
  Clock3,
  CloudRain,
  Compass,
  Gauge,
  Leaf,
  Map as MapIcon,
  RadioTower,
  RefreshCcw,
  Route,
  ShieldCheck,
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
type Tone = "neutral" | "good" | "bad";

const windows = ["Solo ora selezionata", "Mattina", "Pranzo", "Pomeriggio", "Giornata intera"];

const pollutantLabels: Record<string, string> = {
  pm10: "Particolato PM10",
  "pm2.5": "Particolato PM2.5",
  no2: "Biossido di azoto",
  o3: "Ozono",
};

const defaultControls: ScenarioControls = {
  traffic_reduction: 0.2,
  wind_multiplier: 1.0,
  rain_event: false,
  focus_zone: "all",
  green_improvement: 0,
  window_label: "Solo ora selezionata",
};

const railSections = [
  { id: "overview", label: "Panoramica", icon: <Gauge size={16} /> },
  { id: "map", label: "Mappa", icon: <MapIcon size={16} /> },
  { id: "scenario", label: "Scenario", icon: <SlidersHorizontal size={16} /> },
  { id: "observations", label: "Punti chiave", icon: <Activity size={16} /> },
  { id: "reliability", label: "Dati", icon: <ShieldCheck size={16} /> },
];

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

function formatSignedNumber(value: number | undefined, fractionDigits = 2) {
  if (value === undefined || Number.isNaN(value)) return "n/d";
  return `${value > 0 ? "+" : ""}${formatNumber(value, fractionDigits)}`;
}

function formatSignedPercent(value: number | undefined, fractionDigits = 0) {
  if (value === undefined || Number.isNaN(value)) return "n/d";
  return `${value > 0 ? "+" : ""}${value.toLocaleString("it-IT", {
    maximumFractionDigits: fractionDigits,
    minimumFractionDigits: fractionDigits,
  })}%`;
}

function deltaTone(value: number | undefined): Tone {
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

function mean(values: number[]) {
  if (!values.length) return undefined;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function humanizeZone(value: string) {
  if (!value) return "Campus";
  return value
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function humanizeConfidence(value?: string) {
  if (!value) return "stabile";
  const normalized = value.toLowerCase();
  if (normalized.includes("alta") || normalized.includes("high")) return "alta";
  if (normalized.includes("media") || normalized.includes("medium")) return "media";
  if (normalized.includes("bassa") || normalized.includes("low")) return "bassa";
  return value;
}

function reliabilityFromLabel(value?: string) {
  if (!value) return 0.7;
  const normalized = value.toLowerCase();
  if (normalized.includes("alta") || normalized.includes("high")) return 0.92;
  if (normalized.includes("media") || normalized.includes("medium")) return 0.75;
  if (normalized.includes("bassa") || normalized.includes("low")) return 0.48;
  return 0.7;
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
    buildings: { color: "#465147", weight: 1, fillColor: "#657066", fillOpacity: 0.18, opacity: 0.3 },
    green: { color: "#6f9a61", weight: 1, fillColor: "#7cab6a", fillOpacity: 0.28, opacity: 0.38 },
    roads: { color: "#897967", weight: 2, opacity: 0.42 },
    parking: { color: "#ad8453", weight: 1, fillColor: "#dbb37a", fillOpacity: 0.28, opacity: 0.55 },
    transport: { color: "#5d7f8f", weight: 2, fillColor: "#5d7f8f", fillOpacity: 0.2, opacity: 0.7 },
    zones: { color: "#32453a", weight: 2, fillOpacity: mode === "delta" ? 0.15 : 0.05, opacity: 0.48 },
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
              fillOpacity: mode === "delta" ? 0.44 : mode === "scenario" ? 0.36 : 0.28,
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
          <GeoJSON
            key="transport"
            data={mapData.layers.transport as never}
            style={layerStyle.transport}
            pointToLayer={(_feature, latlng) => L.circleMarker(latlng, { radius: 5, ...layerStyle.transport })}
          />
        ) : null}
        {zones ? <GeoJSON key={`zones-${mode}`} data={zones as never} style={layerStyle.zones} /> : null}
        {mapData?.stations.map((station, index) => (
          <CircleMarker
            key={`station-${index}`}
            center={[station.lat, station.lon]}
            radius={6}
            pathOptions={{ color: "#ffffff", fillColor: "#70869a", fillOpacity: 0.9, weight: 2 }}
          >
            <Popup>{station.station_name ?? station.name ?? "Stazione ARPAC"}</Popup>
          </CircleMarker>
        ))}
        {sensors.map((sensor, index) => {
          const delta = sensor.delta ?? 0;
          const fillColor = mode === "delta" ? (delta < 0 ? "#5f8a4f" : "#cf8452") : mode === "scenario" ? "#567a5b" : "#2c3e33";
          return (
            <CircleMarker
              key={`${sensor.sensor_name}-${index}`}
              center={[sensor.lat, sensor.lon]}
              radius={8}
              pathOptions={{ color: "#fffdf6", fillColor, fillOpacity: 0.96, weight: 3 }}
            >
              <Popup>
                <strong>{sensor.sensor_name}</strong>
                <br />
                Zona: {humanizeZone(sensor.zone)}
                <br />
                Valore: {formatNumber(sensor.scenario_value ?? sensor.estimated_value, 2)}
                {sensor.delta !== undefined ? (
                  <>
                    <br />
                    Delta: {formatSignedNumber(sensor.delta, 2)}
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

  if (!points.length) return <div className="empty-line">Andamento non disponibile</div>;
  return (
    <svg className="timeline" viewBox="0 0 100 100" role="img" aria-label="Confronto tra situazione attuale e scenario">
      <path d={pathFor("baseline")} className="line baseline" />
      <path d={pathFor("scenario")} className="line scenario" />
    </svg>
  );
}

function SummaryCard({
  eyebrow,
  title,
  value,
  note,
  icon,
  tone = "neutral",
}: {
  eyebrow: string;
  title: string;
  value: string;
  note: string;
  icon: ReactNode;
  tone?: Tone;
}) {
  return (
    <article className={`summary-card ${tone}`}>
      <div>
        <span className="card-eyebrow">{eyebrow}</span>
        <strong>{title}</strong>
        <p>{value}</p>
        <small>{note}</small>
      </div>
      <div className="summary-icon">{icon}</div>
    </article>
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
  const [controls, setControls] = useState<ScenarioControls>(defaultControls);

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

  const zoneLabels = useMemo(() => {
    const next = new Map<string, string>();
    summary?.zones.forEach((zone) => next.set(zone.id, zone.label));
    return next;
  }, [summary]);

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

  const currentPollutantLabel = pollutantLabels[pollutant.toLowerCase()] ?? pollutant.toUpperCase();
  const activeSnapshot = useMemo(() => {
    if (mode !== "baseline" && scenario?.snapshot.length) return scenario.snapshot;
    return mapData?.snapshot ?? [];
  }, [mapData, mode, scenario]);

  const impactPercent = useMemo(() => {
    if (!scenario?.timeline.length) return undefined;
    const baselineAverage = mean(scenario.timeline.map((point) => point.baseline));
    if (!baselineAverage) return undefined;
    return (scenario.summary.mean_delta / baselineAverage) * 100;
  }, [scenario]);

  const bestZone = useMemo(() => {
    const candidate = [...(scenario?.zone_summary ?? [])]
      .filter((zone) => Number.isFinite(zone.mean_delta))
      .sort((a, b) => a.mean_delta - b.mean_delta)[0];
    if (!candidate) return undefined;
    return { ...candidate, label: zoneLabels.get(candidate.zone) ?? humanizeZone(candidate.zone) };
  }, [scenario, zoneLabels]);

  const attentionZone = useMemo(() => {
    const candidate = [...(scenario?.zone_summary ?? [])]
      .filter((zone) => Number.isFinite(zone.mean_delta))
      .sort((a, b) => b.mean_delta - a.mean_delta)[0];
    if (!candidate) return undefined;
    return { ...candidate, label: zoneLabels.get(candidate.zone) ?? humanizeZone(candidate.zone) };
  }, [scenario, zoneLabels]);

  const topSensors = useMemo(() => {
    return [...activeSnapshot]
      .sort((a, b) =>
        mode === "delta"
          ? (a.delta ?? 0) - (b.delta ?? 0)
          : (b.scenario_value ?? b.estimated_value) - (a.scenario_value ?? a.estimated_value),
      )
      .slice(0, 5);
  }, [activeSnapshot, mode]);

  const hotspotSensor = useMemo(() => {
    return [...activeSnapshot]
      .sort((a, b) => (b.scenario_value ?? b.estimated_value) - (a.scenario_value ?? a.estimated_value))[0];
  }, [activeSnapshot]);

  const improvementSensor = useMemo(() => {
    return [...(scenario?.snapshot ?? [])]
      .filter((sensor) => sensor.delta !== undefined)
      .sort((a, b) => (a.delta ?? 0) - (b.delta ?? 0))[0];
  }, [scenario]);

  const zoneRows = useMemo(() => {
    return [...(scenario?.zone_summary ?? [])]
      .filter((zone) => Number.isFinite(zone.mean_delta))
      .sort((a, b) => a.mean_delta - b.mean_delta)
      .slice(0, 5)
      .map((zone) => ({
        ...zone,
        label: zoneLabels.get(zone.zone) ?? humanizeZone(zone.zone),
      }));
  }, [scenario, zoneLabels]);

  const reliabilityScore = useMemo(() => {
    const snapshot = mapData?.snapshot ?? [];
    if (!snapshot.length) return undefined;
    const values = snapshot.map((sensor) => reliabilityFromLabel(sensor.confidence_label));
    return Math.round((mean(values) ?? 0) * 100);
  }, [mapData]);

  const observationNotes = useMemo(() => {
    const notes: Array<{ tone: Tone; text: string }> = [];
    if (hotspotSensor) {
      notes.push({
        tone: "bad",
        text: `${hotspotSensor.sensor_name} mostra il valore piu alto in ${zoneLabels.get(hotspotSensor.zone) ?? humanizeZone(hotspotSensor.zone)}.`,
      });
    }
    if (improvementSensor && improvementSensor.delta !== undefined) {
      notes.push({
        tone: deltaTone(improvementSensor.delta),
        text: `${improvementSensor.sensor_name} e il punto che beneficia di piu dello scenario (${formatSignedNumber(improvementSensor.delta, 2)}).`,
      });
    }
    if (bestZone) {
      notes.push({
        tone: "good",
        text: `${bestZone.label} e l'area con l'esito migliore nel confronto attuale.`,
      });
    }
    return notes.slice(0, 3);
  }, [bestZone, hotspotSensor, improvementSensor, zoneLabels]);

  const narrative = useMemo(() => {
    const delta = scenario?.summary.mean_delta;
    if (delta === undefined) {
      return "Quando scegli un intervento, qui trovi un riassunto in linguaggio semplice dell'effetto stimato sul campus.";
    }

    const change =
      delta < -0.05
        ? "migliorerebbe"
        : delta > 0.05
          ? "peggiorerebbe"
          : "cambierebbe poco";
    const intensity = Math.round(controls.traffic_reduction * 100);
    const greenGain = Math.round(controls.green_improvement * 100);
    const windText = `${controls.wind_multiplier.toFixed(1)}x`;
    const zoneText =
      controls.focus_zone === "all"
        ? "su tutto il campus"
        : `nella zona ${zoneLabels.get(controls.focus_zone) ?? humanizeZone(controls.focus_zone)}`;
    const bestText = bestZone ? `L'effetto piu favorevole si vede in ${bestZone.label}.` : "";
    const attentionText =
      attentionZone && attentionZone.mean_delta > -0.05
        ? `Conviene osservare con attenzione ${attentionZone.label} perche cambia meno delle altre aree.`
        : "";

    return `Con una riduzione del traffico del ${intensity}% ${zoneText}, vento ${windText}${controls.rain_event ? ", presenza di pioggia" : ""}${greenGain ? ` e piu verde (${greenGain}%)` : ""}, la qualita dell'aria ${change} in media di ${formatNumber(Math.abs(delta), 2)}. ${bestText} ${attentionText}`.trim();
  }, [attentionZone, bestZone, controls, scenario, zoneLabels]);

  const selectPreset = (name: string) => {
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

  return (
    <main className="app-shell" data-testid="air-twin-cockpit">
      <aside className="rail">
        <div className="rail-brand">
          <div className="rail-mark">
            <Leaf size={18} />
          </div>
          <div>
            <strong>UNISA</strong>
            <span>Air Quality Digital Twin</span>
          </div>
        </div>

        <nav className="rail-nav" aria-label="Sezioni schermata">
          {railSections.map((item, index) => (
            <a key={item.id} className={index === 0 ? "rail-link active" : "rail-link"} href={`#${item.id}`}>
              {item.icon}
              <span>{item.label}</span>
            </a>
          ))}
        </nav>

        <div className="rail-status">
          <div className="rail-status-card">
            <span className="card-eyebrow">Situazione rapida</span>
            <strong>{controls.rain_event ? "Pioggia considerata" : "Nessuna pioggia"}</strong>
            <p>Vento {controls.wind_multiplier.toFixed(1)}x</p>
            <p>Traffico -{Math.round(controls.traffic_reduction * 100)}%</p>
          </div>
          <button className="refresh-button" onClick={() => window.location.reload()}>
            <RefreshCcw size={16} />
            Aggiorna dati
          </button>
          <small>Ultimo aggiornamento {formatTime(summary?.latest_timestamp ?? timestamp)}</small>
        </div>
      </aside>

      <section className="main-panel">
        <header className="hero-header" id="overview">
          <div>
            <h1>Operazioni ambientali campus</h1>
            <p>Questa schermata ti mostra la qualita dell'aria stimata sul campus e l'effetto di possibili interventi.</p>
          </div>
          <div className="hero-meta">
            <span className="meta-chip">
              <Clock3 size={15} />
              {formatTime(timestamp)}
            </span>
            <span className="meta-chip">Open data</span>
            <span className="meta-chip">{mapData?.snapshot.length ?? 0} sensori</span>
            {isPending ? <span className="meta-chip loading">Aggiornamento</span> : null}
          </div>
        </header>

        <section className="summary-grid">
          <SummaryCard
            eyebrow="Inquinante e ora"
            title={pollutant.toUpperCase()}
            value={formatTime(timestamp)}
            note={currentPollutantLabel}
            icon={<CloudRain size={20} />}
          />
          <SummaryCard
            eyebrow="Stima effetto scenario"
            title={formatSignedNumber(scenario?.summary.mean_delta, 2)}
            value={impactPercent !== undefined ? `${formatSignedPercent(impactPercent)} rispetto alla media` : "Confronto sul campus"}
            note={scenario ? "Differenza media tra situazione attuale e intervento" : "n/d"}
            icon={scenario && (scenario.summary.mean_delta ?? 0) <= 0 ? <ArrowDownRight size={20} /> : <ArrowUpRight size={20} />}
            tone={deltaTone(scenario?.summary.mean_delta)}
          />
          <SummaryCard
            eyebrow="Zona migliore"
            title={bestZone?.label ?? "In attesa dati"}
            value={bestZone ? `Delta medio ${formatSignedNumber(bestZone.mean_delta, 2)}` : "n/d"}
            note="Area con l'esito piu favorevole in questo scenario"
            icon={<CheckCircle2 size={20} />}
            tone="good"
          />
        </section>

        {error ? (
          <div className="error-banner">
            <AlertTriangle size={18} /> {error}
          </div>
        ) : null}

        <section className="map-card" id="map">
          <div className="map-card-head">
            <div className="mode-switch" aria-label="Modalita mappa">
              <button className={mode === "baseline" ? "active" : ""} onClick={() => setMode("baseline")}>
                Situazione attuale
              </button>
              <button className={mode === "scenario" ? "active" : ""} onClick={() => setMode("scenario")}>
                Intervento simulato
              </button>
              <button className={mode === "delta" ? "active" : ""} onClick={() => setMode("delta")}>
                Differenza
              </button>
            </div>
            <div className="map-legend">
              <span>Come leggere la mappa</span>
              <div className="legend-scale">
                <i className="legend-dot good" />
                <small>Migliora</small>
                <i className="legend-dot neutral" />
                <small>Quasi invariato</small>
                <i className="legend-dot bad" />
                <small>Peggiora</small>
              </div>
            </div>
          </div>

          <div className="map-stage">
            <CampusMap mapData={mapData} scenario={scenario} mode={mode} />
            <div className="map-overlay map-caption">
              <div>
                <strong>
                  {mode === "delta"
                    ? "Differenza rispetto alla situazione attuale"
                    : mode === "scenario"
                      ? "Effetto dell'intervento selezionato"
                      : "Situazione stimata sul campus"}
                </strong>
                <span>
                  Verde indica un miglioramento stimato; i toni piu caldi indicano aree dove il valore resta alto o cresce.
                </span>
              </div>
            </div>
            <div className="map-overlay map-compass">
              <Compass size={16} />
              <span>N</span>
            </div>
            <div className="map-overlay map-footnote">
              <span>Mappa stimata</span>
              <strong>Risoluzione media (24)</strong>
            </div>
          </div>
        </section>

        <section className="insight-grid" id="observations">
          <article className="insight-card">
            <div className="insight-card-head">
              <EyeCardIcon />
              <div>
                <h2>Punti da osservare</h2>
                <p>Tre letture rapide per orientarti senza entrare nei dettagli tecnici.</p>
              </div>
            </div>
            <div className="observation-list">
              {observationNotes.map((note, index) => (
                <div key={`${note.text}-${index}`} className="observation-item">
                  <i className={`legend-dot ${note.tone}`} />
                  <span>{note.text}</span>
                </div>
              ))}
            </div>
          </article>

          <article className="insight-card">
            <div className="insight-card-head">
              <BarChart3 size={18} />
              <div>
                <h2>Confronto per zona</h2>
                <p>Le zone con il delta medio piu marcato per {pollutant.toUpperCase()}.</p>
              </div>
            </div>
            <div className="zone-comparison">
              {zoneRows.map((zone) => (
                <div key={zone.zone} className="zone-row">
                  <div>
                    <strong>{zone.label}</strong>
                    <span>{zone.sensors} sensori virtuali</span>
                  </div>
                  <div className="zone-value">
                    <b className={deltaTone(zone.mean_delta)}>{formatSignedNumber(zone.mean_delta, 2)}</b>
                    <i style={{ width: `${Math.min(Math.abs(zone.mean_delta) * 38, 100)}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </article>

          <article className="insight-card" id="reliability">
            <div className="insight-card-head">
              <ShieldCheck size={18} />
              <div>
                <h2>Affidabilita dei dati</h2>
                <p>Una lettura sintetica di copertura, fonti aperte e validazione.</p>
              </div>
            </div>
            <div className="reliability-body">
              <div
                className="reliability-ring"
                style={{ ["--score" as string]: `${reliabilityScore ?? 0}%` }}
                aria-label="Affidabilita stimata"
              >
                <strong>{reliabilityScore ?? "n/d"}%</strong>
              </div>
              <div className="reliability-copy">
                <p>
                  Confidenza media {topSensors[0]?.confidence_label ? humanizeConfidence(topSensors[0].confidence_label) : "stabile"} con{" "}
                  {mapData?.snapshot.length ?? 0} sensori disponibili.
                </p>
                <ul>
                  <li>Stazioni ARPAC usate: {summary?.stations ?? "n/d"}</li>
                  <li>Righe modello disponibili: {summary?.rows.toLocaleString("it-IT") ?? "n/d"}</li>
                  <li>
                    Validazione open-data:{" "}
                    {summary?.validation?.overall?.mae !== undefined && summary.validation.overall.mae !== null
                      ? `MAE ${summary.validation.overall.mae.toFixed(2)}`
                      : "n/d"}
                  </li>
                </ul>
              </div>
            </div>
          </article>
        </section>
      </section>

      <aside className="guide-panel" id="scenario">
        <section className="step-card">
          <div className="step-head">
            <span>1</span>
            <div>
              <h2>Scegli inquinante e ora</h2>
              <p>Seleziona il fenomeno che vuoi osservare e il momento da analizzare.</p>
            </div>
          </div>

          <label>
            <span className="field-label">Inquinante</span>
            <select value={pollutant} onChange={(event) => setPollutant(event.target.value)}>
              {summary?.pollutants.map((item) => (
                <option key={item} value={item}>
                  {item.toUpperCase()} - {pollutantLabels[item.toLowerCase()] ?? item.toUpperCase()}
                </option>
              ))}
            </select>
          </label>

          <label>
            <span className="field-label">Data e ora</span>
            <select value={timestamp ?? ""} onChange={(event) => setTimestamp(event.target.value)}>
              {timestamps.map((item) => (
                <option key={item} value={item}>
                  {formatTime(item)}
                </option>
              ))}
            </select>
          </label>
        </section>

        <section className="step-card">
          <div className="step-head">
            <span>2</span>
            <div>
              <h2>Scegli l'intervento</h2>
              <p>Usa un preset gia pronto oppure adatta intensita, area e durata della simulazione.</p>
            </div>
          </div>

          <label>
            <span className="field-label">Scenario suggerito</span>
            <select onChange={(event) => selectPreset(event.target.value)} value={selectedPresetName}>
              {summary?.presets.map((preset) => (
                <option key={preset.name}>{preset.name}</option>
              ))}
            </select>
          </label>

          <label className="range-field">
            <span className="field-row">
              <span className="field-label">Riduzione traffico</span>
              <strong>-{Math.round(controls.traffic_reduction * 100)}%</strong>
            </span>
            <input
              type="range"
              min="0"
              max="0.5"
              step="0.05"
              value={controls.traffic_reduction}
              onChange={(event) => updateScenarioControls({ ...controls, traffic_reduction: Number(event.target.value) })}
            />
          </label>

          <label className="range-field">
            <span className="field-row">
              <span className="field-label">Più vento</span>
              <strong>{controls.wind_multiplier.toFixed(1)}x</strong>
            </span>
            <input
              type="range"
              min="0.5"
              max="2"
              step="0.1"
              value={controls.wind_multiplier}
              onChange={(event) => updateScenarioControls({ ...controls, wind_multiplier: Number(event.target.value) })}
            />
          </label>

          <label className="range-field">
            <span className="field-row">
              <span className="field-label">Più verde</span>
              <strong>+{Math.round(controls.green_improvement * 100)}%</strong>
            </span>
            <input
              type="range"
              min="0"
              max="0.5"
              step="0.05"
              value={controls.green_improvement}
              onChange={(event) => updateScenarioControls({ ...controls, green_improvement: Number(event.target.value) })}
            />
          </label>

          <label>
            <span className="field-label">Zona di interesse</span>
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
            <span className="field-label">Durata dell'effetto</span>
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
            className={controls.rain_event ? "toggle-button active" : "toggle-button"}
            onClick={() => updateScenarioControls({ ...controls, rain_event: !controls.rain_event })}
          >
            <CloudRain size={16} />
            {controls.rain_event ? "Pioggia considerata" : "Aggiungi pioggia"}
          </button>
        </section>

        <section className="step-card">
          <div className="step-head">
            <span>3</span>
            <div>
              <h2>Leggi il risultato</h2>
              <p>Qui trovi il confronto tra situazione attuale e scenario in forma compatta.</p>
            </div>
          </div>

          <div className={`result-card ${deltaTone(scenario?.summary.mean_delta)}`}>
            <div>
              <span className="card-eyebrow">Miglioramento stimato</span>
              <strong>{formatSignedNumber(scenario?.summary.mean_delta, 2)}</strong>
              <p>Delta medio campus ({pollutant.toUpperCase()})</p>
            </div>
            <div className="result-icon">
              {scenario && (scenario.summary.mean_delta ?? 0) <= 0 ? <ArrowDownRight size={20} /> : <ArrowUpRight size={20} />}
            </div>
          </div>

          <div className="timeline-panel">
            <div className="timeline-head">
              <span>Andamento atteso</span>
              <small>{controls.window_label}</small>
            </div>
            <Timeline points={scenario?.timeline ?? []} />
            <div className="legend">
              <span>
                <i className="baseline-swatch" />
                situazione attuale
              </span>
              <span>
                <i className="scenario-swatch" />
                intervento simulato
              </span>
            </div>
          </div>
        </section>

        <section className="brief-card">
          <div className="brief-head">
            <Leaf size={18} />
            <div>
              <h2>In breve</h2>
              <p>Il riassunto interpretativo da condividere con chi non vuole leggere tutta la dashboard.</p>
            </div>
          </div>
          <p>{narrative}</p>
          <div className="brief-tags">
            <span>Traffico -{Math.round(controls.traffic_reduction * 100)}%</span>
            <span>Vento {controls.wind_multiplier.toFixed(1)}x</span>
            <span>Verde +{Math.round(controls.green_improvement * 100)}%</span>
            {controls.rain_event ? <span>Pioggia inclusa</span> : null}
          </div>
        </section>
      </aside>
    </main>
  );
}

function EyeCardIcon() {
  return (
    <div className="icon-badge">
      <Activity size={18} />
    </div>
  );
}

export default App;
