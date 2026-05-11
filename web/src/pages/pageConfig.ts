export type PageId = "overview" | "twin-core" | "map" | "scenarios" | "sensors" | "insights" | "data-center" | "settings";

export const pageItems: Array<{ id: PageId; label: string; helper: string }> = [
  { id: "overview", label: "Overview", helper: "Stato e azioni" },
  { id: "twin-core", label: "Twin Core", helper: "Asset/state" },
  { id: "map", label: "Mappa", helper: "Zone e layer" },
  { id: "scenarios", label: "Scenari", helper: "What-if" },
  { id: "sensors", label: "Sensori", helper: "Explorer" },
  { id: "insights", label: "Insights", helper: "Trend e forecast" },
  { id: "data-center", label: "Data Center", helper: "Job/export" },
  { id: "settings", label: "Settings", helper: "Health/admin" },
];
