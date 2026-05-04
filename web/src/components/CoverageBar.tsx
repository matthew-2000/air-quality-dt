import { coverageText, formatPercent, pollutantLabels } from "../format";
import type { CoverageRow } from "../types";

export function CoverageBar({ row, selected, onSelect }: { row: CoverageRow; selected: boolean; onSelect: () => void }) {
  const label = pollutantLabels[row.pollutant] ?? row.pollutant.toUpperCase();
  return (
    <button className={selected ? "coverage-row active" : "coverage-row"} onClick={onSelect} aria-pressed={selected}>
      <div className="coverage-copy">
        <strong>{label}</strong>
        <span>{coverageText(row.active_sensors, row.capable_sensors)}</span>
      </div>
      <div
        className="coverage-meter"
        role="meter"
        aria-label={`Copertura ${label}`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(row.coverage_ratio * 100)}
      >
        <i style={{ width: `${Math.max(8, Math.round(row.coverage_ratio * 100))}%` }} />
      </div>
      <small>{formatPercent(row.coverage_ratio)}</small>
    </button>
  );
}
