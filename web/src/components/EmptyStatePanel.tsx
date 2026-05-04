import { formatNumber } from "../format";
import type { Summary } from "../types";

export function EmptyStatePanel({
  summary,
  observationRows,
}: {
  summary: Summary;
  observationRows?: number;
}) {
  return (
    <section className="panel empty-state-panel" aria-live="polite">
      <div className="panel-head">
        <div>
          <span>Dati non ancora disponibili</span>
          <h2>Nessuna osservazione sensore acquisita</h2>
        </div>
      </div>
      <p>
        Il catalogo contiene {summary.sensors} sensori, ma lo store operativo non ha ancora letture normalizzate.
        Avvia l'ingestione MQTT e poi aggiorna la dashboard.
      </p>
      <div className="dataset-grid">
        <div>
          <span>Sensori registrati</span>
          <strong>{summary.sensors}</strong>
        </div>
        <div>
          <span>Osservazioni archiviate</span>
          <strong>{formatNumber(observationRows, 0)}</strong>
        </div>
        <div>
          <span>Stato feed live</span>
          <strong>
            {summary.live_feed?.status === "unconfigured"
              ? "non configurato"
              : summary.live_feed?.status === "stale"
                ? "stale"
                : summary.live_feed?.status ?? "n/d"}
          </strong>
        </div>
        <div>
          <span>Comando operativo</span>
          <strong>make data-live</strong>
        </div>
      </div>
    </section>
  );
}
