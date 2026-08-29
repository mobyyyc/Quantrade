import { spawn } from "node:child_process";
import path from "node:path";
import { getLatestDatedScores } from "@/lib/research-read-model";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function userFacingError(output: string): string {
  if (output.includes("available after the regular market closes")) {
    return "The daily update is available after the regular market closes at 4:00 p.m. Toronto time.";
  }
  if (output.includes("No current S&P 500 universe")) {
    return "Today’s S&P 500 universe is not ready yet. Try again after the daily data refresh.";
  }
  if (output.includes("already running")) {
    return "A daily update is already running. Keep this page open and try again when it finishes.";
  }
  if (output.includes("SEC filing ingestion failed")) {
    return "SEC filing retrieval or validation did not complete. The update stopped safely before publication; no duplicate scores were created.";
  }
  return "The daily update did not complete. Check the local research service logs for details.";
}

export async function POST() {
  const workspaceRoot = process.env.QUANTRADE_WORKSPACE_ROOT
    ?? (process.cwd().endsWith(path.join("apps", "web")) ? path.resolve(process.cwd(), "../..") : process.cwd());
  const envFile = path.join(workspaceRoot, ".env");
  let result: { code: number | null; output: string };
  try {
    result = await new Promise<{ code: number | null; output: string }>((resolve, reject) => {
      const child = spawn("py", ["-3.14", "-m", "quantrade_research.manual_daily_update", "--env-file", envFile], {
        cwd: workspaceRoot,
        env: { ...process.env, PYTHONPATH: path.join(workspaceRoot, "services", "research", "src") },
        windowsHide: true,
      });
      let output = "";
      child.stdout.on("data", (chunk) => { output += String(chunk); });
      child.stderr.on("data", (chunk) => { output += String(chunk); });
      child.on("error", reject);
      child.on("close", (code) => resolve({ code, output }));
    });
  } catch (error) {
    console.error("[daily-update] failed to start research process", { error });
    return Response.json(
      { error: "The local research process could not be started. Check the web terminal for details." },
      { status: 500 },
    );
  }
  if (result.code !== 0) {
    console.error("[daily-update] research process failed", {
      code: result.code,
      output: result.output.slice(-4_000),
    });
    return Response.json({ error: userFacingError(result.output) }, { status: 500 });
  }
  if (result.output.includes("already_completed")) {
    return Response.json({ message: "Today’s canonical score publication already exists. No duplicate update was run." });
  }
  try {
    const latest = await getLatestDatedScores();
    const eligibleCount = latest?.scores.filter((score) => score.eligible).length ?? 0;
    const totalCount = latest?.scores.length ?? 0;
    return Response.json({
      message: "Daily update completed. The canonical score publication is ready to view.",
      result: latest ? { scoreDate: latest.scoreDate, eligibleCount, totalCount } : undefined,
    });
  } catch {
    return Response.json({ message: "Daily update completed. The canonical score publication is ready to view." });
  }
}
