import path from "node:path";

export type DailyUpdateLaunchSpec = {
  executable: string;
  args: string[];
  cwd: string;
};

export function resolveWorkspaceRoot(cwd = process.cwd()): string {
  return process.env.QUANTRADE_WORKSPACE_ROOT
    ?? (cwd.endsWith(path.join("apps", "web")) ? path.resolve(cwd, "../..") : cwd);
}

export function dailyUpdateLaunchSpec(workspaceRoot = resolveWorkspaceRoot()): DailyUpdateLaunchSpec {
  const scriptPath = path.join(workspaceRoot, "scripts", "run-daily-update.ps1");
  const envFile = path.join(workspaceRoot, ".env");
  return {
    executable: process.env.QUANTRADE_POWERSHELL ?? "powershell.exe",
    args: [
      "-NoLogo",
      "-NoProfile",
      "-NonInteractive",
      "-ExecutionPolicy",
      "Bypass",
      "-File",
      scriptPath,
      "-EnvFile",
      envFile,
    ],
    cwd: workspaceRoot,
  };
}
