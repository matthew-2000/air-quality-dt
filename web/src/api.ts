const API_BASE = import.meta.env.VITE_API_BASE ?? "";

function apiUrl(path: string) {
  return `${API_BASE}${path}`;
}

export async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), init);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

export function openEventStream(path: string): EventSource {
  return new EventSource(apiUrl(path));
}

export function requestMessage(reason: unknown) {
  return reason instanceof Error ? reason.message : "Richiesta non riuscita";
}
