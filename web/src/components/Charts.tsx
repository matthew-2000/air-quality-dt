import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatNumber, formatTime, pollutantLabels, pollutantUnits } from "../format";
import type { ForecastWindow, HistoryPoint, TrendPoint } from "../types";

function axisTime(value: string) {
  return formatTime(value);
}

export function EmptyChart({ children }: { children: string }) {
  return <div className="chart-empty chart-empty-strong">{children}</div>;
}

export function SensorHistoryChart({ points, pollutant }: { points: HistoryPoint[]; pollutant: string }) {
  if (!points.length) {
    return <EmptyChart>Storico non disponibile per il sensore selezionato.</EmptyChart>;
  }
  const unit = pollutantUnits[pollutant] ?? "";
  const data = points.map((point) => ({
    time: point.timestamp,
    value: point.estimated_value,
    temperature: point.temperature,
    humidity: point.humidity,
  }));
  return (
    <div className="chart-card" role="img" aria-label={`Storico ${pollutantLabels[pollutant] ?? pollutant.toUpperCase()}`}>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={data} margin={{ top: 16, right: 18, bottom: 8, left: 0 }}>
          <CartesianGrid stroke="rgba(37, 48, 40, 0.08)" vertical={false} />
          <XAxis dataKey="time" tickFormatter={axisTime} tickLine={false} axisLine={false} minTickGap={24} />
          <YAxis tickLine={false} axisLine={false} width={42} tickFormatter={(value) => formatNumber(Number(value), 0)} />
          <Tooltip
            contentStyle={{ borderRadius: 12, border: "1px solid rgba(37,48,40,.12)" }}
            labelFormatter={(value) => `Timestamp ${formatTime(String(value))}`}
            formatter={(value) => [`${formatNumber(Number(value), 2)} ${unit}`, pollutantLabels[pollutant] ?? pollutant.toUpperCase()]}
          />
          <Legend verticalAlign="top" height={28} />
          <Line type="monotone" dataKey="value" name={`${pollutantLabels[pollutant] ?? pollutant.toUpperCase()} ${unit}`} stroke="#256c4f" strokeWidth={2.5} dot={{ r: 3 }} activeDot={{ r: 5 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function AnalyticsTrendChart({ points }: { points: TrendPoint[] }) {
  if (!points.length) {
    return <EmptyChart>Trend campus non disponibile nello storico corrente.</EmptyChart>;
  }
  return (
    <div className="chart-card">
      <ResponsiveContainer width="100%" height={230}>
        <LineChart data={points} margin={{ top: 16, right: 18, bottom: 8, left: 0 }}>
          <CartesianGrid stroke="rgba(37, 48, 40, 0.08)" vertical={false} />
          <XAxis dataKey="timestamp" tickFormatter={axisTime} tickLine={false} axisLine={false} minTickGap={24} />
          <YAxis tickLine={false} axisLine={false} width={42} tickFormatter={(value) => formatNumber(Number(value), 0)} />
          <Tooltip
            contentStyle={{ borderRadius: 12, border: "1px solid rgba(37,48,40,.12)" }}
            labelFormatter={(value) => `Timestamp ${formatTime(String(value))}`}
          />
          <Legend verticalAlign="top" height={28} />
          <Line type="monotone" dataKey="mean_value" name="Media" stroke="#256c4f" strokeWidth={2.4} dot={false} />
          <Line type="monotone" dataKey="max_value" name="Massimo" stroke="#c1772a" strokeWidth={1.8} dot={false} />
          <Line type="monotone" dataKey="min_value" name="Minimo" stroke="#2c5f88" strokeWidth={1.8} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ForecastBandChart({ windows }: { windows: ForecastWindow[] }) {
  if (!windows.length) {
    return <EmptyChart>Forecast non disponibile. Aggiorna dati o verifica sensori online.</EmptyChart>;
  }
  const data = windows.map((window) => ({
    label: `${window.minutes} min`,
    expected: window.expected_value,
    lower: window.lower,
    upper: window.upper,
    confidence: window.confidence,
  }));
  return (
    <div className="chart-card forecast-chart-card">
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={data} margin={{ top: 16, right: 18, bottom: 8, left: 0 }}>
          <CartesianGrid stroke="rgba(37, 48, 40, 0.08)" vertical={false} />
          <XAxis dataKey="label" tickLine={false} axisLine={false} />
          <YAxis tickLine={false} axisLine={false} width={42} tickFormatter={(value) => formatNumber(Number(value), 0)} />
          <Tooltip
            contentStyle={{ borderRadius: 12, border: "1px solid rgba(37,48,40,.12)" }}
            formatter={(value, name) => [formatNumber(Number(value), 2), name === "expected" ? "Valore atteso" : name === "upper" ? "Banda alta" : "Banda bassa"]}
          />
          <Legend verticalAlign="top" height={28} />
          <Area type="monotone" dataKey="upper" name="Banda alta" stroke="transparent" fill="rgba(37,108,79,.12)" />
          <Area type="monotone" dataKey="lower" name="Banda bassa" stroke="transparent" fill="#fff" />
          <Line type="monotone" dataKey="expected" name="Valore atteso" stroke="#256c4f" strokeWidth={2.6} dot={{ r: 4 }} />
          <ReferenceLine y={0} stroke="rgba(37,48,40,.2)" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
