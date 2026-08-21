import { spawn } from "node:child_process";
import path from "node:path";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function userFacingError(output: string): string {
  if (output.includes("available after the regular market closes")) {
    return "The daily update is available after the regular market closes at 4:00 p.m. Toronto time.";
  }
  if (output.includes("No current S&P 500 universe")) {
    return "Today’s S&P 500 universe is not ready yet. Try again after the daily data refresh.";
  }
  return "The daily update did not complete. Check the local research service logs for details.";
}

export async function POST() {
  const workspaceRoot = process.env.QUANTRADE_WORKSPACE_ROOT
    ?? (process.cwd().endsWith(path.join("apps", "web")) ? path.resolve(process.cwd(), "../..") : process.cwd());
  const result = await new Promise<{ code: number | null; output: string }>((resolve, reject) => {
    const child = spawn("py", ["-3.14", "-m", "quantrade_research.manual_daily_update"], {
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
  if (result.code !== 0) {
    return Response.json({ error: userFacingError(result.output) }, { status: 500 });
  }
  return Response.json({ message: "Daily update completed. Scores are ready to view." });
}
