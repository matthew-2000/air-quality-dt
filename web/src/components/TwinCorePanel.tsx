import { GitBranch, Network, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { getJson, requestMessage } from "../api";
import { ageLabel, formatNumber, formatPercent } from "../format";
import type { TwinAssetsPayload, TwinStatePayload, TwinValidationPayload } from "../types";

function statusCopy(status?: string) {
  if (status === "operational") return "operativo";
  if (status === "degraded") return "degradato";
  if (status === "validated") return "validato";
  if (status === "pending") return "in attesa";
  if (status === "insufficient_data") return "dati insufficienti";
  return status ?? "n/d";
}

export function TwinCorePanel({ pollutant, timestamp }: { pollutant: string; timestamp: string | null }) {
  const [assets, setAssets] = useState<TwinAssetsPayload | null>(null);
  const [state, setState] = useState<TwinStatePayload | null>(null);
  const [validation, setValidation] = useState<TwinValidationPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!pollutant) return;
    const query = `pollutant=${encodeURIComponent(pollutant)}${timestamp ? `&timestamp=${encodeURIComponent(timestamp)}` : ""}`;
    Promise.all([
      getJson<TwinAssetsPayload>("/api/twin/assets"),
      getJson<TwinStatePayload>(`/api/twin/state?${query}`),
      getJson<TwinValidationPayload>(`/api/twin/validation?${query}`),
    ])
      .then(([assetPayload, statePayload, validationPayload]) => {
        setAssets(assetPayload);
        setState(statePayload);
        setValidation(validationPayload);
        setError(null);
      })
      .catch((reason) => setError(requestMessage(reason)));
  }, [pollutant, timestamp]);

  const mappedAssets = Object.values(assets?.counts ?? {}).reduce((total, value) => total + value, 0);

  return (
    <section className="twin-core-grid" id="twin-core">
      <article className="panel twin-core-panel">
        <div className="panel-head">
          <div>
            <span>Twin Core</span>
            <h2>Stato canonico del campus</h2>
          </div>
          <Network size={18} />
        </div>
        {error ? <p className="job-error">{error}</p> : null}
        <div className="dataset-grid">
          <div>
            <span>Asset modellati</span>
            <strong>{formatNumber(mappedAssets, 0)}</strong>
          </div>
          <div>
            <span>Relazioni</span>
            <strong>{formatNumber(assets?.relationships.length, 0)}</strong>
          </div>
          <div>
            <span>Stato</span>
            <strong>{statusCopy(state?.status)}</strong>
          </div>
          <div>
            <span>Copertura</span>
            <strong>{formatPercent(state?.quality.coverage_ratio)}</strong>
          </div>
        </div>
        <p className="method-note">
          Registro fisico + stato osservato: sensori, zone e layer campus sono collegati in una vista macchina, non solo grafica.
        </p>
      </article>

      <article className="panel twin-core-panel">
        <div className="panel-head">
          <div>
            <span>State estimation</span>
            <h2>Qualità e gap</h2>
          </div>
          <ShieldCheck size={18} />
        </div>
        <div className="dataset-grid">
          <div>
            <span>Sensori attivi</span>
            <strong>
              {formatNumber(state?.quality.active_sensors, 0)} / {formatNumber(state?.quality.capable_sensors, 0)}
            </strong>
          </div>
          <div>
            <span>Età mediana</span>
            <strong>{ageLabel(state?.quality.median_age_seconds ?? undefined)}</strong>
          </div>
          <div>
            <span>Incertezza media</span>
            <strong>{formatNumber(state?.quality.mean_uncertainty, 3)}</strong>
          </div>
          <div>
            <span>Feed</span>
            <strong>{state?.quality.feed_status ?? "n/d"}</strong>
          </div>
        </div>
        <div className="driver-list">
          {(state?.gaps ?? []).map((gap) => (
            <span key={`${gap.type}-${gap.detail}`}>{gap.detail}</span>
          ))}
          {!state?.gaps.length ? <span>nessun gap critico nel timestamp selezionato</span> : null}
        </div>
      </article>

      <article className="panel twin-core-panel">
        <div className="panel-head">
          <div>
            <span>Validation</span>
            <h2>Forecast vs realtà</h2>
          </div>
          <GitBranch size={18} />
        </div>
        <div className="dataset-grid">
          <div>
            <span>Stato</span>
            <strong>{statusCopy(validation?.status)}</strong>
          </div>
          <div>
            <span>Finestre validate</span>
            <strong>{formatNumber(validation?.metrics.validated_windows, 0)}</strong>
          </div>
          <div>
            <span>MAE</span>
            <strong>{formatNumber(validation?.metrics.mae, 3)}</strong>
          </div>
          <div>
            <span>Bias</span>
            <strong>{formatNumber(validation?.metrics.bias, 3)}</strong>
          </div>
        </div>
        <p className="method-note">Backtest sulle osservazioni successive disponibili. Se non esistono misure future, la validazione resta pending.</p>
      </article>
    </section>
  );
}
