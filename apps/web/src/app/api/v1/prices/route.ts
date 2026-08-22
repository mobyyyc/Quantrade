import { getLatestPriceSummaries, ResearchReadModelError } from "@/lib/research-read-model";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export async function GET(request: Request) {
  const values = (new URL(request.url).searchParams.get("securityIds") ?? "")
    .split(",")
    .map((value) => value.trim())
    .filter((value) => uuidPattern.test(value))
    .slice(0, 50);
  if (!values.length) return Response.json({ prices: [] });
  try {
    return Response.json({ prices: await getLatestPriceSummaries(values) }, {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    const status = error instanceof ResearchReadModelError ? error.status : 500;
    return Response.json({ error: "Unable to load latest prices." }, { status });
  }
}
