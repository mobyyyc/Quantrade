import { ResearchReadModelError, searchSecurities } from "@/lib/research-read-model";
import { AuthError, authErrorResponse, authorizeApiRequest } from "@/lib/auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try { await authorizeApiRequest(request); } catch (error) { return authErrorResponse(error); }
  const query = new URL(request.url).searchParams.get("query")?.trim() ?? "";
  if (!query) {
    return Response.json({ results: [] });
  }
  try {
    return Response.json({ results: await searchSecurities(query) }, {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    if (error instanceof AuthError) return authErrorResponse(error);
    const status = error instanceof ResearchReadModelError ? error.status : 500;
    return Response.json({ error: "Unable to search companies." }, { status });
  }
}
