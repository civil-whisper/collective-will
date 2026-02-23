import {auth} from "@/lib/auth";

export async function getBackendAccessToken(): Promise<string | null> {
  const session = await auth();
  return session?.backendAccessToken ?? null;
}

export function buildBearerHeaders(accessToken: string): Record<string, string> {
  return {Authorization: `Bearer ${accessToken}`};
}
