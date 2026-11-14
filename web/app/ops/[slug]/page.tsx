import { Suspense } from "react";
import OpsRoom from "@/components/ops/OpsRoom";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { connection } from "next/server";
import { auth, roleOf } from "@/lib/auth";

export default function OpsPage({ params }: PageProps<"/ops/[slug]">) {
  return (
    <Suspense fallback={<div className="grid-bg h-screen" />}>
      <Ops params={params} />
    </Suspense>
  );
}

async function Ops({ params }: { params: PageProps<"/ops/[slug]">["params"] }) {
  const { slug } = await params;
  await connection();  // rendu à la requête : la session (lue par Better Auth avec l'heure courante) n'est pas pré-rendue
  const session = await auth.api.getSession({ headers: await headers() });
  const role = session ? roleOf(session.user) : "demo";  // visiteur : démo publique
  let label = slug;
  let found = false;
  try {
    const r = await fetch(`${process.env.BACKEND_URL ?? "http://localhost:8010"}/api/events/${slug}`,
      { cache: "no-store", headers: { "x-internal-token": process.env.BACKEND_TOKEN ?? "", "x-viewer-role": role } });
    if (r.ok) { label = (await r.json()).label ?? slug; found = true; }
  } catch {}
  if (role === "demo" && !found) redirect("/");  // observation non publiée : invisible pour la démo
  return <OpsRoom slug={slug} label={label} />;
}
