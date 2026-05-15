import { Download, HeartPulse, SlidersHorizontal } from "lucide-react";
import { useEffect, useState } from "react";
import { getJson } from "../api";
import { formatDateTime } from "../format";
import type { OperationalHealthPayload, Summary } from "../types";

function statusTone(status: string) {
  if (["ok", "live", "available", "scheduled"].includes(status)) return "good";
  if (["running", "queued", "stale", "unknown", "manual"].includes(status)) return "neutral";
  return "warn";
}

export function OperationsPanel({ summary }: { summary: Summary | null }) {
  const [health, setHealth] = useState<OperationalHealthPayload | null>(null);

  useEffect(() => {
    getJson<OperationalHealthPayload>("/api/ops/health")
      .then(setHealth)
      .catch(() => setHealth(null));
  }, [summary?.latest_received_at]);

  const services = health?.services ?? [];
  const latestIngest = health?.backup.last_backup ?? summary?.ingestion?.generated_at ?? null;

  return (
    <section className="admin-grid" id="operations">
      <article className="panel health-panel">
        <div className="panel-head">
          <div>
            <span>Health</span>
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
          {!services.length ? <div className="chart-empty">Health non disponibile.</div> : null}
        </div>
      </article>

      <article className="panel settings-panel">
        <div className="panel-head">
          <div>
            <span>Configurazione</span>
            <h2>Stato operativo reale</h2>
          </div>
          <SlidersHorizontal size={18} />
        </div>
        <div className="settings-grid">
          <div>
            <span>MQTT</span>
            <strong>{summary?.live_feed?.configured ? "Configurato" : "Da configurare"}</strong>
          </div>
          <div>
            <span>Ultimo ingest</span>
            <strong>{formatDateTime(latestIngest)}</strong>
          </div>
          <div>
            <span>Store operativo</span>
            <strong>{services.some((service) => service.name === "DB operativo" && service.status === "ok") ? "SQLite attivo" : "Non verificato"}</strong>
          </div>
          <div>
            <span>Backup</span>
            <strong>{health?.backup.status === "manual" ? "Manuale" : health?.backup.status ?? "Non configurato"}</strong>
          </div>
        </div>
      </article>

      <article className="panel export-panel">
        <div className="panel-head">
          <div>
            <span>Export</span>
            <h2>Dati scaricabili</h2>
          </div>
          <Download size={18} />
        </div>
        <div className="export-command-list">
          <a className="export-link" href="/api/export/observations?format=csv">
            <Download size={14} />
            Osservazioni CSV
          </a>
          <a className="export-link" href="/api/export/sensors?format=json">
            <Download size={14} />
            Sensori JSON
          </a>
          <a className="export-link" href="/api/export/raw-messages?format=csv">
            <Download size={14} />
            MQTT raw CSV
          </a>
        </div>
        <p className="method-note">Il cockpit esporta osservazioni, catalogo sensori e messaggi raw. Nessun layer di forecast o scenario viene più mantenuto.</p>
      </article>
    </section>
  );
}
