import { Database, Download, RefreshCcw } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { getJson, requestMessage } from "../api";
import { formatTime } from "../format";
import type { DataSourceList, DataSourceStatus, ProductJob, ProductJobList } from "../types";

type JobAction = {
  label: string;
  description: string;
  endpoint: string;
};

const actions: JobAction[] = [
  {
    label: "Ascolta live 10s",
    description: "Acquisisce MQTT on-demand e aggiorna gli snapshot senza loop permanente.",
    endpoint: "/api/jobs/live-ingest?duration_seconds=10&max_messages=25",
  },
  {
    label: "Aggiorna snapshot",
    description: "Ricostruisce la vista operativa dai dati gia' acquisiti.",
    endpoint: "/api/jobs/refresh",
  },
  {
    label: "Ricostruisci dataset",
    description: "Rilegge lo storico MQTT raw e normalizza le osservazioni.",
    endpoint: "/api/jobs/snapshots",
  },
  {
    label: "Aggiorna contesto",
    description: "Aggiorna sensori, zone e layer campus.",
    endpoint: "/api/jobs/context",
  },
  {
    label: "Arricchisci fonti",
    description: "Scarica Open-Meteo e ricalcola meteo, verde, traffico e background.",
    endpoint: "/api/jobs/enrich",
  },
];

const exports = [
  { label: "Osservazioni CSV", href: "/api/export/observations?format=csv" },
  { label: "Sensori JSON", href: "/api/export/sensors?format=json" },
  { label: "MQTT raw CSV", href: "/api/export/raw-messages?format=csv" },
];

function statusLabel(status: ProductJob["status"]) {
  if (status === "queued") return "in coda";
  if (status === "running") return "in corso";
  if (status === "completed") return "completato";
  return "fallito";
}

function hasActiveJob(jobs: ProductJob[]) {
  return jobs.some((job) => job.status === "queued" || job.status === "running");
}

export function DataJobsPanel({ onDataChanged }: { onDataChanged: () => void }) {
  const [jobs, setJobs] = useState<ProductJob[]>([]);
  const [sources, setSources] = useState<DataSourceStatus[]>([]);
  const [busyEndpoint, setBusyEndpoint] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const notifiedJobs = useRef<Set<string>>(new Set());

  const active = useMemo(() => hasActiveJob(jobs), [jobs]);

  const loadJobs = () => {
    getJson<ProductJobList>("/api/jobs")
      .then((payload) => {
        setJobs(payload.jobs);
        setError(null);
        const newCompletedJobs = payload.jobs.filter((job) => job.status === "completed" && !notifiedJobs.current.has(job.job_id));
        if (newCompletedJobs.length) {
          newCompletedJobs.forEach((job) => notifiedJobs.current.add(job.job_id));
          onDataChanged();
          loadSources();
        }
      })
      .catch((reason) => setError(requestMessage(reason)));
  };

  const loadSources = () => {
    getJson<DataSourceList>("/api/sources")
      .then((payload) => setSources(payload.sources))
      .catch(() => setSources([]));
  };

  useEffect(() => {
    loadJobs();
    loadSources();
  }, []);

  useEffect(() => {
    if (!active) return;
    const timer = globalThis.setInterval(loadJobs, 2500);
    return () => globalThis.clearInterval(timer);
  }, [active]);

  const startJob = (action: JobAction) => {
    setBusyEndpoint(action.endpoint);
    getJson<ProductJob>(action.endpoint, { method: "POST" })
      .then((job) => {
        setJobs((current) => [job, ...current.filter((item) => item.job_id !== job.job_id)]);
        setError(null);
        loadSources();
      })
      .catch((reason) => setError(requestMessage(reason)))
      .finally(() => setBusyEndpoint(null));
  };

  return (
    <article className="panel provenance-panel data-jobs-panel">
      <div className="panel-head">
        <div>
          <span>Gestione dati</span>
          <h2>Operazioni prodotto</h2>
        </div>
        <Database size={18} />
      </div>

      <div className="job-action-grid">
        {actions.map((action) => (
          <button
            type="button"
            className="job-action"
            key={action.endpoint}
            onClick={() => startJob(action)}
            disabled={busyEndpoint !== null || active}
          >
            <strong>{busyEndpoint === action.endpoint ? "Avvio..." : action.label}</strong>
            <span>{action.description}</span>
          </button>
        ))}
      </div>

      {error ? <p className="job-error">{error}</p> : null}

      <div className="source-list">
        {sources.map((source) => (
          <div className={`source-row ${source.status}`} key={source.source_id}>
            <div>
              <strong>{source.label}</strong>
              <span>{source.features !== undefined ? `${source.features} feature` : source.source_url}</span>
            </div>
            <div>
              <span>{source.status}</span>
              <small>{formatTime(source.fetched_at ?? null)}</small>
            </div>
          </div>
        ))}
      </div>

      <div className="export-grid">
        {exports.map((item) => (
          <a className="export-link" href={item.href} key={item.href}>
            <Download size={14} />
            {item.label}
          </a>
        ))}
      </div>

      <div className="job-list">
        {jobs.slice(0, 4).map((job) => (
          <div className={`job-row ${job.status}`} key={job.job_id}>
            <div>
              <strong>{job.name}</strong>
              <span>{job.message ?? "Operazione dati"}</span>
              {job.error ? <span className="job-error-text">{job.error}</span> : null}
            </div>
            <div>
              <span>{statusLabel(job.status)}</span>
              <small>{formatTime(job.finished_at ?? job.started_at)}</small>
            </div>
          </div>
        ))}
        {!jobs.length ? (
          <div className="job-empty">
            <RefreshCcw size={15} />
            <span>Nessuna operazione avviata in questa sessione.</span>
          </div>
        ) : null}
      </div>
    </article>
  );
}
