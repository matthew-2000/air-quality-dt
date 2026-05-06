import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  ClipboardList,
  CloudRain,
  Download,
  Gauge,
  HeartPulse,
  History,
  Save,
  Settings,
  SlidersHorizontal,
  Sparkles,
  Wind,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { getJson, postJson, requestMessage } from "../api";
import { formatDateTime, formatNumber, formatPercent, pollutantLabels } from "../format";
import type {
  DecisionSupportPayload,
  ForecastPayload,
  OperationalHealthPayload,
  ScenarioRun,
  ScenarioRunList,
  Summary,
} from "../types";

const scenarioOptions = [
  { id: "traffic_increase", label: "Aumento traffico", icon: <BarChart3 size={15} /> },
  { id: "traffic_reduction", label: "Riduzione traffico", icon: <Gauge size={15} /> },
  { id: "campus_event", label: "Evento campus", icon: <Sparkles size={15} /> },
  { id: "parking_closure", label: "Chiusura parcheggio", icon: <AlertTriangle size={15} /> },
  { id: "new_sensor", label: "Nuovo sensore", icon: <CheckCircle2 size={15} /> },
  { id: "sensor_offline", label: "Sensore offline", icon: <AlertTriangle size={15} /> },
  { id: "rain", label: "Pioggia", icon: <CloudRain size={15} /> },
  { id: "wind", label: "Vento", icon: <Wind size={15} /> },
  { id: "green_increase", label: "Aumento verde", icon: <Sparkles size={15} /> },
  { id: "freshness_window", label: "Finestra freschezza", icon: <SlidersHorizontal size={15} /> },
];

function scenarioLabel(id: string) {
  return scenarioOptions.find((option) => option.id === id)?.label ?? id.replaceAll("_", " ");
}

function statusTone(status: string) {
  if (["ok", "live", "available", "scheduled"].includes(status)) return "good";
  if (["running", "queued", "stale", "unknown"].includes(status)) return "neutral";
  return "warn";
}

function ProductTooltip({ label, children }: { label: string; children: string }) {
  return (
    <span className="info-tooltip" tabIndex={0} aria-label={`${label}: ${children}`}>
      {label}
      <span role="tooltip">{children}</span>
    </span>
  );
}

function ForecastDecisionPanel({ pollutant, timestamp }: { pollutant: string; timestamp: string | null }) {
  const [forecast, setForecast] = useState<ForecastPayload | null>(null);
  const [decision, setDecision] = useState<DecisionSupportPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!pollutant) return;
    const query = `pollutant=${encodeURIComponent(pollutant)}${timestamp ? `&timestamp=${encodeURIComponent(timestamp)}` : ""}`;
    Promise.all([
      getJson<ForecastPayload>(`/api/forecast?${query}`),
      getJson<DecisionSupportPayload>(`/api/decision-support?${query}`),
    ])
      .then(([forecastPayload, decisionPayload]) => {
        setForecast(forecastPayload);
        setDecision(decisionPayload);
        setError(null);
      })
      .catch((reason) => setError(requestMessage(reason)));
  }, [pollutant, timestamp]);

  return (
    <section className="decision-grid" id="insights">
      <article className="panel decision-panel">
        <div className="panel-head">
          <div>
            <span>Forecast</span>
            <h2>Prossime 3 ore</h2>
          </div>
          <small>{forecast?.method ?? "baseline statistica"}</small>
        </div>
        {error ? <p className="job-error">{error}</p> : null}
        <div className="forecast-list">
          {(forecast?.windows ?? []).map((window) => (
            <div className="forecast-row" key={window.minutes}>
              <div>
                <strong>{window.minutes} min</strong>
                <span>{window.trend}</span>
              </div>
              <div>
                <strong>{formatNumber(window.expected_value, 2)}</strong>
                <span>
                  {formatNumber(window.lower, 2)} - {formatNumber(window.upper, 2)}
                </span>
              </div>
              <span className={`status-pill ${window.risk === "alto" ? "warn" : window.risk === "medio" ? "neutral" : "good"}`}>
                rischio {window.risk}
              </span>
            </div>
          ))}
          {!forecast?.windows.length ? <div className="chart-empty">Forecast non disponibile. Avvia una simulazione o aggiorna dati dalla dashboard.</div> : null}
        </div>
      </article>

      <article className="panel decision-panel">
        <div className="panel-head">
          <div>
            <span>Decision support</span>
            <h2>Cosa fare ora</h2>
          </div>
          <small>rischio {decision?.risk_level ?? "n/d"}</small>
        </div>
        <div className="action-list">
          {(decision?.what_to_do_now ?? []).map((item) => (
            <div key={item}>
              <ClipboardList size={15} />
              <span>{item}</span>
            </div>
          ))}
        </div>
        <div className="alert-list">
          {(decision?.alerts ?? []).map((alert) => (
            <div className={`alert-row ${alert.level}`} key={`${alert.title}-${alert.detail}`}>
              <strong>{alert.title}</strong>
              <span>{alert.detail}</span>
            </div>
          ))}
        </div>
      </article>

      <article className="panel decision-panel glossary-panel">
        <div className="panel-head">
          <div>
            <span>Glossario</span>
            <h2>Termini chiave</h2>
          </div>
        </div>
        <div className="glossary-list">
          <ProductTooltip label="AQI">Indice sintetico di qualità aria. Più alto significa più attenzione operativa.</ProductTooltip>
          <ProductTooltip label="Confidence">Quanto fidarsi del dato: copertura sensori, freschezza e coerenza.</ProductTooltip>
          <ProductTooltip label="Anomalia">Misura inattesa: picco, drift, dato mancante o arrivo in ritardo.</ProductTooltip>
          <ProductTooltip label="Forecast">Stima breve termine utile per decidere ora, non previsione meteo lunga.</ProductTooltip>
          <ProductTooltip label="Delta scenario">Differenza tra baseline reale e snapshot simulato non distruttivo.</ProductTooltip>
          <ProductTooltip label="Retention">Tempo di conservazione dati prima di cleanup programmato.</ProductTooltip>
        </div>
      </article>
    </section>
  );
}

function ScenarioStudio({ pollutant, timestamp }: { pollutant: string; timestamp: string | null }) {
  const [scenarioType, setScenarioType] = useState("traffic_increase");
  const [intensity, setIntensity] = useState(1);
  const [runs, setRuns] = useState<ScenarioRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<ScenarioRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadRuns = () => {
    getJson<ScenarioRunList>("/api/scenarios/runs")
      .then((payload) => {
        setRuns(payload.runs);
        setSelectedRun((current) => current ?? payload.runs[0] ?? null);
      })
      .catch(() => setRuns([]));
  };

  useEffect(loadRuns, []);

  const runScenario = () => {
    setBusy(true);
    postJson<ScenarioRun>("/api/scenarios/run", {
      name: scenarioLabel(scenarioType),
      scenario_type: scenarioType,
      pollutant,
      timestamp,
      intensity,
      parameters: { ui: "dashboard", saved: true },
    })
      .then((run) => {
        setSelectedRun(run);
        setRuns((current) => [run, ...current.filter((item) => item.run_id !== run.run_id)]);
        setError(null);
      })
      .catch((reason) => setError(requestMessage(reason)))
      .finally(() => setBusy(false));
  };

  const topDeltas = selectedRun?.output.zone_deltas?.slice(0, 4) ?? [];

  return (
    <section className="scenario-section" id="scenarios">
      <article className="panel scenario-builder">
        <div className="panel-head">
          <div>
            <span>Scenari</span>
            <h2>Simula senza toccare dati reali</h2>
          </div>
          <small>{pollutantLabels[pollutant] ?? pollutant.toUpperCase()} · baseline {formatDateTime(timestamp)}</small>
        </div>

        <div className="scenario-type-grid">
          {scenarioOptions.map((option) => (
            <button
              key={option.id}
              type="button"
              className={option.id === scenarioType ? "scenario-type active" : "scenario-type"}
              onClick={() => setScenarioType(option.id)}
              aria-pressed={option.id === scenarioType}
            >
              {option.icon}
              {option.label}
            </button>
          ))}
        </div>

        <label className="range-control">
          <span>Intensità intervento</span>
          <input
            type="range"
            min="0"
            max="2"
            step="0.1"
            value={intensity}
            onChange={(event) => setIntensity(Number(event.target.value))}
            aria-label="Intensità scenario"
          />
          <strong>{formatNumber(intensity, 1)}x</strong>
        </label>

        <button type="button" className="primary-action" onClick={runScenario} disabled={busy || !timestamp}>
          <Save size={16} />
          {busy ? "Simulazione..." : "Esegui e salva run"}
        </button>
        {error ? <p className="job-error">{error}</p> : null}
      </article>

      <article className="panel scenario-result">
        <div className="panel-head">
          <div>
            <span>Baseline vs scenario</span>
            <h2>{selectedRun?.name ?? "Nessun run salvato"}</h2>
          </div>
          <small>{selectedRun ? formatDateTime(selectedRun.created_at) : "crea primo scenario"}</small>
        </div>

        {selectedRun ? (
          <>
            <div className="scenario-kpis">
              <div>
                <span>Baseline</span>
                <strong>{formatNumber(selectedRun.output.baseline_mean, 2)}</strong>
              </div>
              <div>
                <span>Scenario</span>
                <strong>{formatNumber(selectedRun.output.scenario_mean, 2)}</strong>
              </div>
              <div>
                <span>Delta</span>
                <strong>{formatNumber(selectedRun.output.delta_mean, 2)}</strong>
              </div>
              <div>
                <span>Confidence</span>
                <strong>{formatPercent(selectedRun.output.confidence)}</strong>
              </div>
            </div>
            <div className="driver-list">
              {(selectedRun.output.drivers ?? []).map((driver) => (
                <span key={driver}>{driver}</span>
              ))}
            </div>
            <div className="zone-delta-list">
              {topDeltas.map((row) => (
                <div key={row.zone}>
                  <strong>{row.zone_name}</strong>
                  <span>{formatNumber(row.delta, 2)}</span>
                </div>
              ))}
            </div>
            <p className="method-note">{selectedRun.output.method_notes}</p>
          </>
        ) : (
          <div className="chart-empty">Nessun run disponibile. Scegli scenario, regola intensità, salva run dalla dashboard.</div>
        )}
      </article>

      <article className="panel scenario-history">
        <div className="panel-head">
          <div>
            <span>Storico scenari</span>
            <h2>Run salvati</h2>
          </div>
          <History size={18} />
        </div>
        <div className="scenario-run-list">
          {runs.map((run) => (
            <button
              type="button"
              key={run.run_id}
              className={selectedRun?.run_id === run.run_id ? "scenario-run active" : "scenario-run"}
              onClick={() => setSelectedRun(run)}
            >
              <strong>{run.name}</strong>
              <span>
                {formatDateTime(run.created_at)} · rischio {run.output.risk ?? "n/d"}
              </span>
            </button>
          ))}
          {!runs.length ? <div className="job-empty">Le simulazioni salvate compariranno qui.</div> : null}
        </div>
      </article>
    </section>
  );
}

function DataCenterSettings({ summary }: { summary: Summary | null }) {
  const [health, setHealth] = useState<OperationalHealthPayload | null>(null);
  const [refreshRate, setRefreshRate] = useState(30);
  const [retention, setRetention] = useState(30);
  const [aqiThreshold, setAqiThreshold] = useState(35);

  useEffect(() => {
    getJson<OperationalHealthPayload>("/api/ops/health")
      .then(setHealth)
      .catch(() => setHealth(null));
  }, [summary?.latest_received_at]);

  const services = health?.services ?? [];
  const exportHref = useMemo(() => `/api/export/observations?format=csv`, []);

  return (
    <section className="admin-grid" id="settings">
      <article className="panel health-panel">
        <div className="panel-head">
          <div>
            <span>Health dashboard</span>
            <h2>Sistema operativo</h2>
          </div>
          <HeartPulse size={18} />
        </div>
        <div className="health-list">
          {services.map((service) => (
            <div key={service.name} className="health-row">
              <span className={`legend-dot ${statusTone(service.status)}`} />
              <div>
                <strong>{service.name}</strong>
                <small>{service.detail ?? service.status}</small>
              </div>
              <span className={`status-pill ${statusTone(service.status)}`}>{service.status}</span>
            </div>
          ))}
          {!services.length ? <div className="chart-empty">Health non disponibile. La dashboard resta in modalità degradata con retry automatico.</div> : null}
        </div>
      </article>

      <article className="panel settings-panel">
        <div className="panel-head">
          <div>
            <span>Settings/Admin</span>
            <h2>Controlli operativi</h2>
          </div>
          <Settings size={18} />
        </div>
        <div className="settings-grid">
          <label>
            <span>Refresh dashboard</span>
            <input type="number" min="10" max="300" value={refreshRate} onChange={(event) => setRefreshRate(Number(event.target.value))} />
          </label>
          <label>
            <span>Retention dati giorni</span>
            <input type="number" min="1" max="365" value={retention} onChange={(event) => setRetention(Number(event.target.value))} />
          </label>
          <label>
            <span>Soglia alert AQI</span>
            <input type="number" min="1" max="500" value={aqiThreshold} onChange={(event) => setAqiThreshold(Number(event.target.value))} />
          </label>
        </div>
        <div className="settings-summary">
          <span>MQTT: {summary?.live_feed?.configured ? "configurato" : "da configurare"}</span>
          <span>Scheduler: ingest, export, cleanup, forecast, backup</span>
          <span>Backup: retention {health?.backup.retention_days ?? retention} giorni</span>
        </div>
      </article>

      <article className="panel export-panel" id="data-center">
        <div className="panel-head">
          <div>
            <span>Data Center</span>
            <h2>Export e report</h2>
          </div>
          <Download size={18} />
        </div>
        <div className="export-command-list">
          <a className="export-link" href={exportHref}>
            <Download size={14} />
            Report osservazioni CSV
          </a>
          <a className="export-link" href="/api/export/sensors?format=json">
            <Download size={14} />
            Sensori JSON
          </a>
          <a className="export-link" href="/api/export/raw-messages?format=csv">
            <Download size={14} />
            Raw MQTT CSV
          </a>
        </div>
        <p className="method-note">Export, job, backup e health sono accessibili da dashboard: niente terminale per flusso utente.</p>
      </article>
    </section>
  );
}

export function ProductWorkflowPanels({
  pollutant,
  timestamp,
  summary,
}: {
  pollutant: string;
  timestamp: string | null;
  summary: Summary | null;
}) {
  return (
    <>
      <ScenarioStudio pollutant={pollutant} timestamp={timestamp} />
      <ForecastDecisionPanel pollutant={pollutant} timestamp={timestamp} />
      <DataCenterSettings summary={summary} />
    </>
  );
}
