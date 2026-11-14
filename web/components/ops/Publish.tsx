"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

interface Pub {
  job: { state: "running" | "done" | "error"; step?: string; error?: string; at: string } | null;
  published: { n: number; at: string | null } | null;
}
const fmt = (iso?: string | null) => (iso ? new Date(iso).toISOString().slice(0, 16).replace("T", " ") + " UTC" : "never");

/** Admin : fige l'état actuel de l'observation pour le compte de démonstration (public). */
export function PublishButton({ slug }: { slug: string }) {
  const [p, setP] = useState<Pub | null>(null);
  const load = () => api<Pub>(`/api/events/${slug}/publication`).then(setP).catch(() => {});
  useEffect(() => { load(); }, [slug]);  // eslint-disable-line react-hooks/exhaustive-deps
  const running = p?.job?.state === "running";
  useEffect(() => {
    if (!running) return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [running]);  // eslint-disable-line react-hooks/exhaustive-deps
  const title = `What the public demo shows. Last published: ${fmt(p?.published?.at)}` +
    (p?.job?.state === "error" ? ` — last attempt failed: ${p.job.error}` : "");
  return (
    <button disabled={running} title={title}
      onClick={async () => { if (!confirm("Publish the current data of this observation to the public demo? It replaces the previous publication.")) return; await api(`/api/events/${slug}/publish`, { method: "POST" }); load(); }}
      className="flex items-center gap-2 rounded-md border border-white/30 px-3 py-1.5 text-[12.5px] font-semibold text-white hover:bg-white/10 disabled:opacity-70">
      {running && <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent" />}
      {running ? `Publishing · ${p?.job?.step ?? ""}` : p?.published ? "Republish for demo" : "Publish for demo"}
    </button>
  );
}

/** Démo : rappelle que les données sont figées et depuis quand. */
export function PublishedBadge({ slug }: { slug: string }) {
  const [p, setP] = useState<Pub | null>(null);
  useEffect(() => { api<Pub>(`/api/events/${slug}/publication`).then(setP).catch(() => {}); }, [slug]);
  return (
    <span className="flex items-center gap-2 text-[12.5px] text-white/80" title="The public demo shows a published snapshot: no live collection, no AI call.">
      <span className="h-2 w-2 rounded-full bg-white/60" />Published data · {fmt(p?.published?.at)}
    </span>
  );
}
