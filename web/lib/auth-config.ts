const DEFAULT_SERVER_API_BASE = "http://localhost:8000";

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, "");
}

export function resolveServerApiBase(env: Record<string, string | undefined> = process.env): string {
  const backendApiBaseUrl = env.BACKEND_API_BASE_URL?.trim();
  if (backendApiBaseUrl) {
    return trimTrailingSlash(backendApiBaseUrl);
  }

  const publicApiBaseUrl = env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (publicApiBaseUrl && /^https?:\/\//i.test(publicApiBaseUrl)) {
    return trimTrailingSlash(publicApiBaseUrl);
  }

  return DEFAULT_SERVER_API_BASE;
}
