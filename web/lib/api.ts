const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function apiPost<T>(path: string, body: object, init?: RequestInit): Promise<T> {
  const mergedHeaders: Record<string, string> = {"content-type": "application/json"};
  if (init?.headers) {
    const extraHeaders = new Headers(init.headers);
    extraHeaders.forEach((value, key) => {
      mergedHeaders[key] = value;
    });
  }
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    method: "POST",
    headers: mergedHeaders,
    body: JSON.stringify(body),
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}
