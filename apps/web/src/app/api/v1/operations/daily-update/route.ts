import { spawn } from "node:child_process";
import { dailyUpdateLaunchSpec } from "@/lib/daily-update-launcher";
import {
  parseDailyUpdateProgress,
  type DailyUpdateStreamEvent,
} from "@/lib/daily-update-progress";
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
  if (output.includes("has not been published yet")) {
    return "SEC has not published today’s daily filing index yet. Please retry after 10:00 p.m. Toronto time; no scores were published.";
  }
  if (output.includes("after 3 attempts")) {
    return "A data provider remained unavailable after three safe attempts. No scores were published; try the update again later.";
  }
  if (output.includes("SEC filing ingestion failed")) {
    return "SEC filing retrieval or validation did not complete. The update stopped safely before publication; no duplicate scores were created.";
  }
  return "The daily update did not complete. Check the local research service logs for details.";
}

export async function POST() {
  let launch: ReturnType<typeof dailyUpdateLaunchSpec>;
  try {
    launch = dailyUpdateLaunchSpec();
  } catch (error) {
    console.error("[daily-update] launch configuration failed", { error });
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
        send({ type: "error", error: "The local research process could not be started. Check the web terminal for details." });
        close();
      });
      child.on("close", async (code) => {
        if (childSettled) return;
        childSettled = true;
        const finalProgress = parseDailyUpdateProgress(stdoutBuffer);
        if (finalProgress) send({ type: "progress", progress: finalProgress });
        if (code !== 0) {
          console.error("[daily-update] research process failed", { code, output: output.slice(-4_000) });
          send({ type: "error", error: userFacingError(output) });
          close();
          return;
        }
        if (output.includes("already_completed")) {
          send({ type: "complete", message: "Today’s canonical score publication already exists. No duplicate update was run." });
          close();
          return;
        }
        if (output.includes("skipped score_date=")) {
          send({ type: "complete", message: "No regular market session was available, so no dated publication was created." });
          close();
          return;
        }
        const completionMessage = output.includes("post_publication_error=")
          ? "Daily scores are ready, but portfolio maintenance needs attention. Check the research-service logs before the next run."
          : "Daily update completed. The canonical score publication is ready to view.";
        try {
          const latest = await getLatestDatedScores();
          const eligibleCount = latest?.scores.filter((score) => score.eligible).length ?? 0;
          const totalCount = latest?.scores.length ?? 0;
          send({
            type: "complete",
            message: completionMessage,
            result: latest ? { scoreDate: latest.scoreDate, eligibleCount, totalCount } : undefined,
          });
        } catch {
          send({ type: "complete", message: completionMessage });
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
