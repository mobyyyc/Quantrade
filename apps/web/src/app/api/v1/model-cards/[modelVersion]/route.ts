import { getModelCard, ResearchReadModelError } from "@/lib/research-read-model";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ modelVersion: string }> },
) {
  const { modelVersion } = await params;
  try {
    const modelCard = await getModelCard(modelVersion);
    return modelCard
      ? Response.json({ modelCard }, { headers: { "Cache-Control": "no-store" } })
      : Response.json({ error: "Model card not found." }, { status: 404 });
  } catch (error) {
    const status = error instanceof ResearchReadModelError ? error.status : 500;
    return Response.json({ error: "Unable to load model card." }, { status });
  }
}
