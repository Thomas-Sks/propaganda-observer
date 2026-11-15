import { Suspense } from "react";
import { redirect } from "next/navigation";
import { connection } from "next/server";

/* /showcase : ouvre la première observation publiée dans sa version showcase. */
export const metadata = { robots: { index: false, follow: false } };

export default function ShowcaseIndex() {
  return <Suspense fallback={<div className="h-screen bg-[#02060d]" />}><Go /></Suspense>;
}

async function Go(): Promise<null> {
  await connection();
  let slug: string | null = null;
  try {
    const r = await fetch(`${process.env.BACKEND_URL ?? "http://localhost:8010"}/api/events`,
      { cache: "no-store", headers: { "x-internal-token": process.env.BACKEND_TOKEN ?? "", "x-viewer-role": "demo" } });
    if (r.ok) slug = ((await r.json()) as { slug: string }[])[0]?.slug ?? null;
  } catch {}
  redirect(slug ? `/showcase/${slug}` : "/");
  return null;
}
