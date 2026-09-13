import { AuthError, authErrorResponse, authorizeApiRequest } from "@/lib/auth";
import { getLatestModelHealth, ResearchReadModelError } from "@/lib/research-read-model";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try { await authorizeApiRequest(request); } catch (error) { return authErrorResponse(error); }
  try {
    const health = await getLatestModelHealth();
    return health
      ? Response.json({ health }, { headers: { "Cache-Control": "no-store" } })
      : Response.json({ error: "No model-health snapshot is available." }, { status: 404 });
  } catch (error) {
    if (error instanceof AuthError) return authErrorResponse(error);
    const status = error instanceof ResearchReadModelError ? error.status : 500;
    return Response.json({ error: "Unable to load model health." }, { status });
  }
}
