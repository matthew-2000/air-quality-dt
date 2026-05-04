export const pollutantLabels: Record<string, string> = {
  pm1: "PM1",
  pm10: "PM10",
  pm25: "PM2.5",
  voc_index: "VOC index",
  nox_index: "NOx index",
};

export const pollutantUnits: Record<string, string> = {
  pm1: "ug/m3",
  pm10: "ug/m3",
  pm25: "ug/m3",
  voc_index: "indice",
  nox_index: "indice",
};

export function formatTime(value: string | null | undefined) {
  if (!value) return "n/d";
  return new Intl.DateTimeFormat("it-IT", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function formatDateTime(value: string | null | undefined) {
  if (!value) return "n/d";
  return new Intl.DateTimeFormat("it-IT", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

export function formatNumber(value: number | null | undefined, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/d";
  return value.toLocaleString("it-IT", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/d";
  return `${Math.round(value * 100)}%`;
}

export function ageLabel(seconds?: number | null) {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return "età n/d";
  if (seconds < 60) return `${seconds}s fa`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min fa`;
  return `${(seconds / 3600).toFixed(1)} h fa`;
}

export function statusLabel(status?: string) {
  if (status === "fresh") return "fresco";
  if (status === "recent") return "recente";
  if (status === "aging") return "in ritardo";
  if (status === "silent") return "silente";
  return "n/d";
}

export function statusTone(status?: string) {
  if (status === "fresh") return "good";
  if (status === "recent") return "neutral";
  if (status === "aging") return "warn";
  return "muted";
}

export function coverageText(active?: number, capable?: number) {
  if (!capable) return `${active ?? 0} sensori`;
  return `${active ?? 0}/${capable} sensori`;
}

export function reliabilityLabel(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/d";
  return `${Math.round(value * 100)}%`;
}

export function pathForValues(values: number[]) {
  if (!values.length) return "";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  return values
    .map((value, index) => {
      const x = 7 + (index / Math.max(values.length - 1, 1)) * 86;
      const y = 84 - ((value - min) / span) * 62;
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}
