"use client";
import { useEffect } from "react";
import { API, api } from "./api";
import { useOps, type Progress } from "./store";

/** SSE : chaque nouveauté (item, histoires recalculées) invalide les vues, qui se rechargent (débit limité). */
export function useEventStream(slug: string, live: boolean) {
  useEffect(() => {
    const s = useOps.getState();
    if (!live) {  // compte de démonstration : données publiées, pas de flux temps réel
      api<Progress>(`/api/events/${slug}/progress`).then(s.setProgress).catch(() => {});
      return;
    }
    let pending: ReturnType<typeof setTimeout> | null = null;
    const invalidate = () => { if (!pending) pending = setTimeout(() => { pending = null; s.bump(); }, 4000); };
    api<Progress>(`/api/events/${slug}/progress`).then(s.setProgress).catch(() => {});
    const es = new EventSource(`${API}/api/stream/${slug}`);
    es.addEventListener("progress", (e) => {
      const p = JSON.parse((e as MessageEvent).data) as Progress;
      const prev = useOps.getState().progress;
      s.setProgress(p);
      // Une étape d'analyse qui se termine = nouvelles narratives disponibles : on recharge les vues
      const fin = (k: string) => p.steps.find((x) => x.key === k)?.state === "done" && prev?.steps.find((x) => x.key === k)?.state !== "done";
      if (fin("narratives") || fin("stance") || fin("video")) s.bump();
    });
    es.onopen = () => s.setConnected(true);
    es.onerror = () => s.setConnected(false);
    es.addEventListener("graph.snapshot", () => s.bump());
    es.addEventListener("item.new", invalidate);
    es.addEventListener("collector.status", (e) => {
      const d = JSON.parse((e as MessageEvent).data);
      s.setStatus(d.state === "running" ? `Collecting · ${d.source}` : d.state === "idle"
        ? `Up to date · +${d.new} new · next pass in ${Math.round(d.next_in_s / 60)} min` : `Error · ${d.source}`);
    });
    return () => { if (pending) clearTimeout(pending); es.close(); };
  }, [slug, live]);
}
