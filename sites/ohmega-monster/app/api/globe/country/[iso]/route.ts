import { NextResponse } from "next/server";

import { countryPanel } from "@/lib/globe-country";

// The /globe country panel's data (internal to the page, not part of the public /api/v1 contract). One country per request.
export const revalidate = 600;

export async function GET(_req: Request, { params }: { params: { iso: string } }): Promise<Response> {
  const panel = await countryPanel(params.iso.toUpperCase());
  if (!panel) return NextResponse.json({ error: "unknown country" }, { status: 404 });
  return NextResponse.json(panel, { headers: { "Cache-Control": "public, s-maxage=600, stale-while-revalidate=3600" } });
}
