import { Activity, Gauge, MapPin, ShieldCheck } from "lucide-react";

import { formatNumber, formatPercent, formatTime, pollutantLabels } from "../format";
import { AnalyticsTrendChart } from "./Charts";
import type { AnalyticsPayload } from "../types";

function flagLabel(flag: string) {
  const labels: Record<string, string> = {
    elevated_value: "valore elevato",
    late_arrival: "arrivo tardivo",
    missing_humidity: "umidità mancante",
    missing_temperature: "temperatura mancante",
    missing_timestamp: "timestamp mancante",
    missing_value: "valore mancante",
    outside_operational_range: "fuori range operativo",
    received_before_measured: "ricezione incoerente",
  };
  return labels[flag] ?? flag.replaceAll("_", " ");
}

function AnalyticsTrend({ analytics }: { analytics?: AnalyticsPayload }) {
  const points = analytics?.trend ?? [];
  const latest = points.at(-1)?.mean_value;
  return (
    <div className="chart-shell compact">
      <div className="chart-summary">
        <div>
          <span>Media ultima finestra</span>
          <strong>{formatNumber(latest, 2)}</strong>
        </div>
        <div>
          <span>Campioni temporali</span>
          <strong>{points.length}</strong>
        </div>
      </div>
      <AnalyticsTrendChart points={points} />
    </div>
  );
}

export function TwinAnalyticsPanel({ analytics }: { analytics?: AnalyticsPayload }) {
  const quality = analytics?.quality;
  const zones = analytics?.zone_summary ?? [];
  const topZone = zones[0];
  const topFlags = quality?.flags.slice(0, 3) ?? [];
  return (
    <section className="analytics-grid" id="analytics">
      <article className="panel analytics-panel">
        <div className="panel-head">
          <div>
            <span>Analytics operative</span>
            <h2>Qualità dato e zone</h2>
          </div>
          <small>{analytics?.timestamp ? `Snapshot ${formatTime(analytics.timestamp)}` : "Snapshot n/d"}</small>
        </div>
        <div className="dataset-grid analytics-kpis">
          <div>
            <span>Qualità OK</span>
            <strong>{formatPercent(quality?.ok_ratio)}</strong>
          </div>
          <div>
            <span>Righe watch</span>
            <strong>{quality?.watch_rows ?? 0}</strong>
          </div>
          <div>
            <span>Righe critiche</span>
            <strong>{quality?.critical_rows ?? 0}</strong>
          </div>
          <div>
            <span>Zona più alta</span>
            <strong>{topZone?.zone_name ?? topZone?.zone ?? "n/d"}</strong>
          </div>
        </div>
        <div className="quality-flag-list">
          {topFlags.length ? (
            topFlags.map((flag) => (
              <div key={flag.flag}>
                <ShieldCheck size={15} />
                <span>{flagLabel(flag.flag)}</span>
                <strong>{flag.rows}</strong>
              </div>
            ))
          ) : (
            <div>
              <ShieldCheck size={15} />
              <span>Nessun flag qualità rilevante</span>
              <strong>ok</strong>
            </div>
          )}
        </div>
      </article>

      <article className="panel analytics-panel">
        <div className="panel-head">
          <div>
            <span>Trend campus</span>
            <h2>{pollutantLabels[analytics?.pollutant ?? ""] ?? analytics?.pollutant?.toUpperCase() ?? "Inquinante"}</h2>
          </div>
        </div>
        <AnalyticsTrend analytics={analytics} />
      </article>

      <article className="panel analytics-panel zone-panel">
        <div className="panel-head">
          <div>
            <span>Zone operative</span>
            <h2>Pressione per area</h2>
          </div>
        </div>
        <div className="zone-list">
          {zones.slice(0, 5).map((zone) => (
            <div key={zone.zone} className="zone-row">
              <div>
                <strong>{zone.zone_name ?? zone.zone}</strong>
                <span>
                  <MapPin size={13} />
                  {zone.sensors ?? 0} sensori
                </span>
              </div>
              <div>
                <span>
                  <Activity size={13} />
                  media {formatNumber(zone.mean_value, 2)}
                </span>
                <span>
                  <Gauge size={13} />
                  qualità {formatPercent(zone.quality_ok_ratio)}
                </span>
              </div>
            </div>
          ))}
          {!zones.length ? <div className="chart-empty">Zone non disponibili nello snapshot selezionato.</div> : null}
        </div>
      </article>
    </section>
  );
}
