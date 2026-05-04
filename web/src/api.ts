const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

export function requestMessage(reason: unknown) {
  return reason instanceof Error ? reason.message : "Richiesta non riuscita";
}
