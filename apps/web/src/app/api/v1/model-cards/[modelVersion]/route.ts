import { getModelCard, ResearchReadModelError } from "@/lib/research-read-model";
import { AuthError, authErrorResponse, authorizeApiRequest } from "@/lib/auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ modelVersion: string }> },
) {
  try {
    await authorizeApiRequest(request);
    const { modelVersion } = await params;
    const modelCard = await getModelCard(modelVersion);
    return modelCard
      ? Response.json({ modelCard }, { headers: { "Cache-Control": "no-store" } })
      : Response.json({ error: "Model card not found." }, { status: 404 });
  } catch (error) {
    if (error instanceof AuthError) return authErrorResponse(error);
    const status = error instanceof ResearchReadModelError ? error.status : 500;
    return Response.json({ error: "Unable to load model card." }, { status });
  }
}
