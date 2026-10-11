import { llmsFull } from "@/lib/api/guide";

// /llms-full.txt: the long machine guide (lib/api/guide.ts), generated from the API's route table and tool list.
export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS

export async function GET(): Promise<Response> {
  return new Response(await llmsFull(), {
    headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "public, s-maxage=300, stale-while-revalidate=3600" },
  });
}
