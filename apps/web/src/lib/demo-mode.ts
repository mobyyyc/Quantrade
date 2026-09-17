import "server-only";

export function isDemoMode(): boolean {
  return process.env.QUANTRADE_DEMO_MODE === "1";
}
