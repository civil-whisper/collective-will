import {NextRequest, NextResponse} from "next/server";

import {buildBearerHeaders, getBackendAccessToken} from "@/lib/backend-auth";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function POST(
  request: NextRequest,
  context: {params: Promise<{submissionId: string}>},
) {
  const accessToken = await getBackendAccessToken();
  if (!accessToken) {
    return NextResponse.json({detail: "unauthorized"}, {status: 401});
  }

  const {submissionId} = await context.params;
  const body = await request.json();
  const response = await fetch(`${API_BASE}/user/dashboard/disputes/${submissionId}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...buildBearerHeaders(accessToken),
    },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  const payload = await response.json();
  return NextResponse.json(payload, {status: response.status});
}
