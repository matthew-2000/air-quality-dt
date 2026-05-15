export type PageId = "overview" | "map" | "sensors" | "insights" | "data-center";

export const pageItems: Array<{ id: PageId; label: string; helper: string }> = [
  { id: "overview", label: "Overview", helper: "Stato operativo" },
  { id: "map", label: "Mappa", helper: "Zone e layer" },
  { id: "sensors", label: "Sensori", helper: "Explorer" },
  { id: "insights", label: "Insights", helper: "Trend e qualità" },
  { id: "data-center", label: "Data Center", helper: "Job, export, health" },
];
