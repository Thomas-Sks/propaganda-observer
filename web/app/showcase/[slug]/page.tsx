import { Suspense } from "react";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { connection } from "next/server";
import OpsRoom from "@/components/ops/OpsRoom";
import IntroLoader from "@/components/intro/IntroLoader";
import { auth, roleOf } from "@/lib/auth";

/* Version « showcase » (URL non liée depuis le site) : même salle d'opérations, mêmes droits,
   avec l'intro, les animations explicatives et le nom Para-Celsus. */
export const metadata = { title: "Programme d'Observer Para-Celsus", robots: { index: false, follow: false } };

export default function ShowcasePage({ params }: PageProps<"/showcase/[slug]">) {
  return (
    <Suspense fallback={<div className="h-screen bg-[#02060d]" />}>
      <Showcase params={params} />
    </Suspense>
  );
}

async function Showcase({ params }: { params: PageProps<"/showcase/[slug]">["params"] }) {
  const { slug } = await params;
  await connection();
  const session = await auth.api.getSession({ headers: await headers() });
  const role = session ? roleOf(session.user) : "demo";
  let label = slug, found = false;
  try {
    const r = await fetch(`${process.env.BACKEND_URL ?? "http://localhost:8010"}/api/events/${slug}`,
      { cache: "no-store", headers: { "x-internal-token": process.env.BACKEND_TOKEN ?? "", "x-viewer-role": role } });
    if (r.ok) { label = (await r.json()).label ?? slug; found = true; }
  } catch {}
  if (role === "demo" && !found) redirect("/");
  return <><IntroLoader /><OpsRoom slug={slug} label={label} showcase /></>;
}
