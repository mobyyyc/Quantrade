import type { ReactNode } from "react";
import { requireAuthenticatedUser } from "@/lib/auth";

export default async function ProtectedLayout({ children }: { children: ReactNode }) {
  await requireAuthenticatedUser();
  return children;
}
