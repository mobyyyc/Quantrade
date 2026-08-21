import { spawn } from "node:child_process";
import path from "node:path";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

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
    return Response.json({ error: result.output.trim() || "The daily update did not complete." }, { status: 500 });
  }
  return Response.json({ message: "Daily update completed. Scores are ready to view." });
}
