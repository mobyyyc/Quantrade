import { listDatedScores, ResearchReadModelError } from "@/lib/research-read-model";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function validDate(value: string | null): value is string {
  return value !== null && /^\d{4}-\d{2}-\d{2}$/.test(value);
}

export async function GET(request: Request) {
  const date = new URL(request.url).searchParams.get("date");
  if (!validDate(date)) {
    return Response.json({ error: "A date query parameter in YYYY-MM-DD format is required." }, { status: 400 });
  }
  try {
    return Response.json({ scoreDate: date, scores: await listDatedScores(date) }, {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    const status = error instanceof ResearchReadModelError ? error.status : 500;
    return Response.json({ error: "Unable to load dated scores." }, { status });
  }
}
