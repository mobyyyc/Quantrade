import { redirect } from "next/navigation";

export default async function PortfolioPage() {
  redirect("/research#track-record");
}
