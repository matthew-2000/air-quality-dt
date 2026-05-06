import type { ReactNode } from "react";

export type LatLon = { lat: number; lon: number };

export type GeoFeature = {
  geometry: { type: string; coordinates: unknown } | null;
  properties?: Record<string, unknown> | null;
};

export type FeatureCollection = { type?: string; features: GeoFeature[] };

export type CoverageRow = {
  pollutant: string;
  active_sensors: number;
  capable_sensors: number;
  coverage_ratio: number;
};

export type SensorHealth = {
  sensor_id: string;
  sensor_name?: string | null;
  status: "fresh" | "recent" | "aging" | "unknown" | "silent";
  latest_received_at?: string | null;
  latest_measured_at?: string | null;
  pollutants: string[];
};

export type Summary = {
  project: string;
  source?: string;
  campus: { name: string; latitude: number; longitude: number };
  pollutants: string[];
  default_pollutant: string;
  latest_timestamp: string | null;
  latest_received_at?: string | null;
  rows: number;
  raw_rows?: number;
  raw_message_rows?: number;
  observation_rows?: number;
  snapshot_rows?: number;
  sensors: number;
  active_sensors?: number;
  capable_sensors?: number;
  coverage_ratio?: number;
  sensor_health?: SensorHealth[];
  coverage_by_pollutant: CoverageRow[];
  layer_counts?: Record<string, number>;
  ingestion?: {
    raw_rows?: number;
    raw_message_rows?: number;
    observation_rows?: number;
    snapshot_rows?: number;
    sensors?: number;
    source?: string;
    generated_at?: string;
    snapshot_bucket_minutes?: number;
    snapshot_freshness_minutes?: number;
  };
  live_feed?: {
    status?: "live" | "stale" | "unconfigured" | "unknown";
    configured?: boolean;
    missing_env?: string[];
    latest_received_at?: string | null;
    age_minutes?: number | null;
  };
  data_sources?: DataSourceStatus[];
  warnings: unknown[];
  mode?: string;
};

export type SnapshotSensor = LatLon & {
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

export type GridCell = {
  polygon: [number, number][];
  color: [number, number, number, number];
  estimated_value?: number;
  reliability?: number;
};

export type MapPayload = {
  snapshot: SnapshotSensor[];
  grid: GridCell[];
  reliability_grid: GridCell[];
  zones: FeatureCollection;
  zone_summary?: ZoneSummaryRow[];
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

export type HistoryPoint = {
  timestamp: string;
  estimated_value: number;
  temperature?: number | null;
  humidity?: number | null;
  num_devices_sniffed?: number | null;
};

export type SensorMetric = {
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

export type SensorDetail = {
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
    traffic_index?: number | null;
    green_index?: number | null;
    wind_speed_10m?: number | null;
    precipitation?: number | null;
    background_value?: number | null;
    background_source?: string | null;
    received_at?: string | null;
  };
};

export type LayerVisibility = Record<"buildings" | "roads" | "green" | "transport" | "parking", boolean>;

export type MapView = "surface" | "sensors" | "coverage";

export type LayerLabel = { id: keyof LayerVisibility; label: string; icon: ReactNode };

export type QualityFlagRow = {
  flag: string;
  rows: number;
};

export type QualitySummary = {
  rows: number;
  ok_rows: number;
  watch_rows: number;
  critical_rows: number;
  ok_ratio: number;
  flags: QualityFlagRow[];
};

export type ZoneSummaryRow = {
  zone: string;
  zone_name?: string;
  mean_value?: number | null;
  max_value?: number | null;
  min_value?: number | null;
  sensors?: number;
  quality_ok_ratio?: number;
  traffic_sensitivity?: number | null;
  green_capacity?: number | null;
};

export type TrendPoint = {
  timestamp: string;
  mean_value: number;
  max_value: number;
  min_value: number;
  sensors: number;
};

export type AnalyticsPayload = {
  pollutant: string;
  timestamp: string | null;
  quality: QualitySummary;
  zone_summary: ZoneSummaryRow[];
  zone_geojson: FeatureCollection;
  trend: TrendPoint[];
};

export type StreamStatus = "connecting" | "live" | "retrying" | "unsupported";

export type LiveStreamEvent = {
  fingerprint: string;
  latest_timestamp: string | null;
  latest_received_at?: string | null;
  snapshot_rows: number;
  observation_rows: number;
  raw_message_rows: number;
  active_sensors: number;
  live_feed_status?: "live" | "stale" | "unconfigured" | "unknown" | null;
  generated_at?: string | null;
};

export type ProductJob = {
  job_id: string;
  name: string;
  status: "queued" | "running" | "completed" | "failed";
  started_at: string;
  finished_at?: string | null;
  message?: string | null;
  result?: Record<string, unknown>;
  error?: string | null;
};

export type ProductJobList = {
  jobs: ProductJob[];
};

export type DataSourceStatus = {
  source_id: string;
  label: string;
  status: string;
  source_url?: string;
  fetched_at?: string | null;
  cache_path?: string | null;
  error?: string | null;
  features?: number;
};

export type DataSourceList = {
  sources: DataSourceStatus[];
};

export type ForecastWindow = {
  minutes: number;
  expected_value: number;
  lower: number;
  upper: number;
  trend: string;
  risk: string;
  confidence: number;
};

export type ForecastPayload = {
  pollutant: string;
  timestamp?: string | null;
  windows: ForecastWindow[];
  critical_zones: Array<Record<string, unknown> | string>;
  method: string;
};

export type ScenarioRun = {
  run_id: string;
  name: string;
  scenario_type: string;
  pollutant: string;
  intensity: number;
  created_at: string;
  baseline_timestamp?: string | null;
  parameters: Record<string, unknown>;
  output: {
    baseline_mean?: number | null;
    scenario_mean?: number | null;
    delta_mean?: number | null;
    confidence?: number | null;
    risk?: string;
    zone_deltas?: Array<{ zone: string; zone_name: string; baseline?: number | null; scenario?: number | null; delta?: number | null }>;
    drivers?: string[];
    areas_to_watch?: string[];
    sensors_to_check?: string[];
    method_notes?: string;
  };
};

export type ScenarioRunList = {
  runs: ScenarioRun[];
};

export type DecisionSupportPayload = {
  risk_level: string;
  what_to_do_now: string[];
  alerts: Array<{ level: string; title: string; detail: string }>;
  suggested_sensor_placement: string[];
  explanations: string[];
};

export type OperationalHealthPayload = {
  services: Array<{ name: string; status: string; detail?: string | null }>;
  backup: { status: string; retention_days: number; restore_test: string; last_backup?: string | null };
};
