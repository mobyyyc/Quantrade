import { redirect } from "next/navigation";
import { authenticatedUser, hasAnyUsers } from "@/lib/auth";
import { SignInForm } from "@/components/sign-in-form";

export const dynamic = "force-dynamic";

export default async function SignInPage({ searchParams }: PageProps<"/sign-in">) {
  if (await authenticatedUser()) redirect("/");
  const setupRequired = !await hasAnyUsers();
  const requested = (await searchParams).next;
  const nextPath = typeof requested === "string" && requested.startsWith("/") && !requested.startsWith("//") ? requested : "/";
  return <main className="auth-page">
    <section className="auth-panel" aria-labelledby="auth-title">
      <span className="brand-mark auth-brand">Q</span>
      <p className="eyebrow">PRIVATE RESEARCH</p>
      <h1 id="auth-title">{setupRequired ? "Secure this workspace." : "Welcome back."}</h1>
      <p>{setupRequired ? "Create the local owner account before Quantrade can expose research or operations." : "Sign in to access your research workspace."}</p>
      <SignInForm setupRequired={setupRequired} nextPath={nextPath} />
    </section>
  </main>;
}
