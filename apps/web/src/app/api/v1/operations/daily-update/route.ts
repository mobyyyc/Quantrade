import { spawn } from "node:child_process";
import { dailyUpdateLaunchSpec } from "@/lib/daily-update-launcher";
import {
  parseDailyUpdateProgress,
  type DailyUpdateStreamEvent,
} from "@/lib/daily-update-progress";
import { getLatestDatedScores } from "@/lib/research-read-model";
import {
  AuthError, auditEvent, authErrorResponse, authorizeApiRequest,
  requestSubject, requireSameOrigin,
} from "@/lib/auth";
import { safeDailyUpdateError } from "@/lib/daily-update-state";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  let user;
  try {
    requireSameOrigin(request);
    user = await authorizeApiRequest(request, "daily_update", 6, 60 * 60);
    if (user.role !== "owner") throw new AuthError("Owner access is required.", 403);
    await auditEvent({ userId: user.userId, eventType: "daily_update", outcome: "allowed", route: "/api/v1/operations/daily-update", subject: requestSubject(request), metadata: { stage: "launch" } });
  } catch (error) {
    return authErrorResponse(error);
  }
  let launch: ReturnType<typeof dailyUpdateLaunchSpec>;
  try {
    launch = dailyUpdateLaunchSpec();
  } catch (error) {
    console.error("[daily-update] launch configuration failed", { error });
    await auditEvent({ userId: user.userId, eventType: "daily_update", outcome: "failed", route: "/api/v1/operations/daily-update", subject: requestSubject(request), metadata: { stage: "configuration" } });
    return Response.json(
      { error: "The local research process could not be configured. Check the web terminal for details." },
      { status: 500 },
    );
  }

  const encoder = new TextEncoder();
  let streamClosed = false;
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const send = (event: DailyUpdateStreamEvent) => {
        if (!streamClosed) controller.enqueue(encoder.encode(`${JSON.stringify(event)}\n`));
      };
      const close = () => {
        if (!streamClosed) {
          streamClosed = true;
          controller.close();
        }
      };
      const child = spawn(launch.executable, launch.args, {
        cwd: launch.cwd,
        env: process.env,
        windowsHide: true,
      });
      let output = "";
      let stdoutBuffer = "";
      let childSettled = false;
      const consumeStdout = (chunk: unknown) => {
        const text = String(chunk);
        output += text;
        stdoutBuffer += text;
        const lines = stdoutBuffer.split(/\r?\n/);
        stdoutBuffer = lines.pop() ?? "";
        for (const line of lines) {
          const progress = parseDailyUpdateProgress(line);
          if (progress) send({ type: "progress", progress });
        }
      };
      child.stdout.on("data", consumeStdout);
      child.stderr.on("data", (chunk) => { output += String(chunk); });
      child.on("error", (error) => {
        childSettled = true;
        console.error("[daily-update] failed to start research process", { error });
        void auditEvent({ userId: user.userId, eventType: "daily_update", outcome: "failed", route: "/api/v1/operations/daily-update", subject: requestSubject(request), metadata: { stage: "spawn" } });
        send({ type: "error", error: "The local research process could not be started. Check the web terminal for details." });
        close();
      });
      child.on("close", async (code) => {
        if (childSettled) return;
        childSettled = true;
        const finalProgress = parseDailyUpdateProgress(stdoutBuffer);
        if (finalProgress) send({ type: "progress", progress: finalProgress });
        const partial = (code === 2 && output.includes("partial_completed score_date="))
          || (code === 0 && output.includes("post_publication_error="));
        if (code !== 0 && !partial) {
          console.error("[daily-update] research process failed", { code, output: output.slice(-4_000) });
          await auditEvent({ userId: user.userId, eventType: "daily_update", outcome: "failed", route: "/api/v1/operations/daily-update", subject: requestSubject(request), metadata: { stage: "research", exitCode: code ?? -1 } });
          send({ type: "error", error: safeDailyUpdateError(output) });
          close();
          return;
        }
        if (output.includes("already_completed")) {
          let result;
          try {
            const latest = await getLatestDatedScores();
            result = latest ? { scoreDate: latest.scoreDate, eligibleCount: latest.scores.filter((score) => score.eligible).length, totalCount: latest.scores.length } : undefined;
          } catch { result = undefined; }
          send({ type: "complete", outcome: "duplicate_prevented", message: "Today’s scores already exist and maintenance is complete. Nothing was recalculated or duplicated.", result });
          close();
          return;
        }
        if (output.includes("skipped score_date=")) {
          send({ type: "complete", outcome: "skipped", message: "No regular market session was available, so no dated publication was created." });
          close();
          return;
        }
        const completionMessage = partial || output.includes("post_publication_error=")
          ? "Scores are ready, but maintenance is pending. Run the update again to retry maintenance without recalculating scores."
          : "Daily update completed. The canonical score publication is ready to view.";
        await auditEvent({ userId: user.userId, eventType: "daily_update", outcome: "allowed", route: "/api/v1/operations/daily-update", subject: requestSubject(request), metadata: { stage: partial ? "partial" : "completed" } });
        try {
          const latest = await getLatestDatedScores();
          const eligibleCount = latest?.scores.filter((score) => score.eligible).length ?? 0;
          const totalCount = latest?.scores.length ?? 0;
          send({
            type: "complete",
            message: completionMessage,
            outcome: partial ? "partial" : "complete",
            result: latest ? { scoreDate: latest.scoreDate, eligibleCount, totalCount } : undefined,
          });
        } catch {
          send({ type: "complete", message: completionMessage, outcome: partial ? "partial" : "complete" });
        }
        close();
      });
    },
    cancel() {
      // The canonical database-backed job continues safely if the browser disconnects.
      streamClosed = true;
    },
  });

  return new Response(stream, {
    headers: {
      "Cache-Control": "no-store",
      "Content-Type": "application/x-ndjson; charset=utf-8",
      "X-Content-Type-Options": "nosniff",
    },
  });
}
