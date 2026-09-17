import { redirect } from "next/navigation";
import { authenticatedUser, hasAnyUsers } from "@/lib/auth";
import { SignInForm } from "@/components/sign-in-form";
import { isDemoMode } from "@/lib/demo-mode";

export const dynamic = "force-dynamic";

export default async function SignInPage({ searchParams }: PageProps<"/sign-in">) {
  if (await authenticatedUser()) redirect("/");
  const setupRequired = !await hasAnyUsers();
  const requested = (await searchParams).next;
  const nextPath = typeof requested === "string" && requested.startsWith("/") && !requested.startsWith("//") ? requested : "/";
  const demoMode = isDemoMode();
  return <main className="auth-page">
    <section className="auth-panel" aria-labelledby="auth-title">
      <span className="brand-mark auth-brand">Q</span>
      <p className="eyebrow">{demoMode ? "SYNTHETIC DEMO" : "PRIVATE RESEARCH"}</p>
      <h1 id="auth-title">{setupRequired ? "Secure this workspace." : "Welcome back."}</h1>
      <p>{setupRequired ? demoMode ? "Create a local demo account. All research values in this workspace are generated fixtures." : "Create the local owner account before Quantrade can expose research or operations." : "Sign in to access your research workspace."}</p>
      <SignInForm setupRequired={setupRequired} nextPath={nextPath} />
    </section>
  </main>;
}
