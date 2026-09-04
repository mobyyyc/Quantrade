import { listDatedScores, ResearchReadModelError } from "@/lib/research-read-model";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function validDate(value: string | null): value is string {
  return value !== null && /^\d{4}-\d{2}-\d{2}$/.test(value);
}

export async function GET(request: Request) {
  const date = new URL(request.url).searchParams.get("date");
  if (!validDate(date)) {
    return Response.json({ error: "A date query parameter in YYYY-MM-DD format is required." }, { status: 400 });
  }
  const requestedIds = new URL(request.url).searchParams.get("securityIds");
  const securityIds = requestedIds
    ? [...new Set(requestedIds.split(",").map((value) => value.trim()).filter((value) => uuidPattern.test(value)))].slice(0, 50)
    : undefined;
  if (requestedIds && !securityIds?.length) return Response.json({ scoreDate: date, scores: [] });
  try {
    return Response.json({ scoreDate: date, scores: await listDatedScores(date, securityIds) }, {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    const status = error instanceof ResearchReadModelError ? error.status : 500;
    return Response.json({ error: "Unable to load dated scores." }, { status });
  }
}
