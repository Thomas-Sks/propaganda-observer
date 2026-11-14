"use client";
import { useMemo, useState } from "react";
import { passes, useOps } from "@/lib/store";
import { useView } from "@/lib/useView";
import { getCoordination, type Coordination as Coord, type CoordCommunity, type CoordEdge, type CoordNode } from "@/lib/views";
import { Empty, PlatformBadge } from "@/components/ui/kit";

/** Une couleur par groupe (dans cet onglet seulement : la légende le dit). */
const COMM = ["#4f46e5", "#0d9488", "#c026d3", "#ea580c", "#0284c7", "#65a30d", "#be123c", "#a16207", "#7c3aed", "#0f766e"];
const commColor = (k: number | null) => (k === null ? "#94a3b8" : COMM[k % COMM.length]);
const KIND = { text: "same text", link: "same link", hashtags: "same hashtags" } as Record<string, string>;
const fmt = (iso: string) => iso.slice(5, 16).replace("T", " ");

export default function Coordination({ slug }: { slug: string }) {
  const { data } = useView(() => getCoordination(slug), [slug]);
  const { filters, openAccount } = useOps();
  const [pairs, setPairs] = useState(false);

  const view = useMemo(() => {
    if (!data) return null;
    const nodes = data.nodes.filter((n) => passes(filters, { platform: n.platform }));
    const ids = new Set(nodes.map((n) => n.id));
    const communities = data.communities.map((c) => ({ ...c, members: c.members.filter((m) => ids.has(m)) })).filter((c) => c.members.length >= 2);
    return { ...data, nodes, communities, edges: data.edges.filter((e) => ids.has(e.source) && ids.has(e.target)) };
  }, [data, filters]);

  if (!view) return <div className="p-8"><Empty text="Computing the coordination network (first load takes ~15 s)…" /></div>;
  const byId = new Map(view.nodes.map((n) => [n.id, n]));
  const big = view.communities.filter((c) => c.members.length >= 3);
  const small = view.communities.filter((c) => c.members.length < 3);
  const shown = pairs ? view.communities : big.length ? big : view.communities;

  return (
    <div className="h-full overflow-y-auto">
      <Header data={view} />
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-line bg-panel-2 px-5 py-2 text-[12.5px] text-muted">
        <b className="text-text">How to read</b>
        <span>Each card is one group of accounts that <span className="text-text">acted together</span>.</span>
        <span><span className="text-text">Line</span> = same text, link or hashtags within {view.window_s}s · <span className="text-text">thicker</span> = more times</span>
        <span>★ listed source · ⚙ automated</span>
        <span><span className="font-semibold text-sev-priority">Red marks</span> lined up vertically = posting at the same moment</span>
        <span className="text-faint">click an account to open it</span>
      </div>
      <div className="mx-auto max-w-[1500px] p-5">
        {!view.communities.length ? <Empty text="No two accounts performed the same action within the coordination window." /> : (
          <>
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
              {shown.map((c) => <GroupCard key={c.id} c={c} data={view} byId={byId} onOpen={openAccount} />)}
            </div>
            {small.length > 0 && big.length > 0 && (
              <button onClick={() => setPairs(!pairs)} className="mt-4 w-full rounded-md border border-line bg-panel py-2.5 text-[13.5px] text-accent hover:bg-panel-2">
                {pairs ? "Hide the pairs" : `Show ${small.length} more pairs of accounts (2 accounts acting together)`}
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function GroupCard({ c, data, byId, onOpen }: { c: CoordCommunity; data: Coord; byId: Map<string, CoordNode>; onOpen: (id: string) => void }) {
  const edges = data.edges.filter((e) => c.members.includes(e.source) && c.members.includes(e.target));
  return (
    <article className="flex flex-col rounded-md border border-line bg-panel">
      <header className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5" style={{ borderTop: `4px solid ${commColor(c.id)}` }}>
        <span className="text-[15px] font-semibold">{c.name}</span>
        <span className="num text-[12px] text-muted">{c.members.length} accounts · {c.strong_edges} strong links{c.first_ts ? ` · ${fmt(c.first_ts)} → ${fmt(c.last_ts!)}` : ""}</span>
        <span className="ml-auto flex gap-1">{Object.keys(c.platforms).map((p) => <PlatformBadge key={p} p={p} />)}
          {c.listed > 0 && <span className="rounded bg-sev-priority/15 px-1.5 text-[11.5px] font-semibold text-sev-priority">★ {c.listed} listed</span>}
          {c.automated > 0 && <span className="rounded bg-sev-review/15 px-1.5 text-[11.5px] font-semibold text-sev-review">⚙ {c.automated} automated</span>}</span>
      </header>
      <div className="px-4 pt-2"><MiniGraph c={c} edges={edges} byId={byId} onOpen={onOpen} /></div>
      <div className="px-4 pb-3">
        <div className="min-w-0 space-y-1.5">
          <div className="text-[11.5px] font-semibold uppercase text-muted">What they shared</div>
          {c.shared.slice(0, 3).map((s, k) => (
            <div key={k} className="rounded bg-panel-2 px-2.5 py-1.5 text-[12.5px]">
              <div className="flex text-[11px] text-muted"><span className="font-semibold uppercase">{KIND[s.kind] ?? s.kind}</span><span className="num ml-auto">{s.accounts} accounts</span></div>
              {s.kind === "link" ? <a href={s.value} target="_blank" rel="noreferrer" className="line-clamp-2 break-all text-accent hover:underline">{s.value}</a>
                : <div className="line-clamp-3 italic">“{s.value}”</div>}
            </div>
          ))}
        </div>
      </div>
      <div className="mt-auto border-t border-line px-4 py-3"><Barcode data={data} members={c.members} onNode={onOpen} /></div>
    </article>
  );
}

/** Petit schéma SVG d'un groupe : comptes en cercle, libellés vers l'extérieur, épaisseur = nombre d'actions communes. */
function MiniGraph({ c, edges, byId, onOpen }: { c: CoordCommunity; edges: CoordEdge[]; byId: Map<string, CoordNode>; onOpen: (id: string) => void }) {
  const n = c.members.length;
  const W = 660, H = n <= 2 ? 150 : 250, cx = W / 2, cy = H / 2;
  const R = n <= 2 ? 40 : Math.min(90, 55 + n * 7);
  const pos = new Map(c.members.map((id, j) => {
    const a = n === 2 ? (j ? Math.PI / 2 : -Math.PI / 2) : (j / n) * Math.PI * 2 - Math.PI / 2;
    return [id, { x: cx + Math.cos(a) * R, y: cy + Math.sin(a) * R, cos: Math.cos(a), sin: Math.sin(a) }];
  }));
  const short = (s: string) => (s.length > 30 ? s.slice(0, 29) + "…" : s);
  const col = commColor(c.id);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="mx-auto h-auto w-full max-w-[660px]">
      {edges.map((e) => {
        const a = pos.get(e.source), b = pos.get(e.target);
        if (!a || !b) return null;
        const ex = e.examples[0];
        return (
          <line key={e.source + e.target} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={e.strong ? "#475569" : "#cbd5e1"} strokeWidth={Math.min(9, 1.5 + e.weight * 1.6)} strokeLinecap="round">
            <title>{`${e.weight} shared action(s)${ex ? ` — e.g. ${KIND[ex.kind]}, ${ex.delay_s}s apart` : ""}`}</title>
          </line>
        );
      })}
      {c.members.map((id) => {
        const p = pos.get(id)!, nd = byId.get(id);
        if (!nd) return null;
        const r = 7 + Math.min(9, Math.sqrt(nd.coordinated_posts) * 1.8);
        // Libellé vers l'extérieur : à droite, à gauche, ou au-dessus / en dessous pour les points du haut et du bas
        const side = n === 2 ? "right" : p.cos > 0.35 ? "right" : p.cos < -0.35 ? "left" : p.sin < 0 ? "top" : "bottom";
        const tx = side === "right" ? p.x + r + 5 : side === "left" ? p.x - r - 5 : p.x;
        const ty = side === "top" ? p.y - r - 7 : side === "bottom" ? p.y + r + 16 : p.y + 5;
        const anchor = side === "right" ? "start" : side === "left" ? "end" : "middle";
        const label = `${nd.listed ? "★ " : ""}${nd.automated ? "⚙ " : ""}${short(nd.label)}`;
        return (
          <g key={id} onClick={() => onOpen(id)} className="cursor-pointer">
            <circle cx={p.x} cy={p.y} r={r} fill={col} stroke="#fff" strokeWidth={2}><title>{`${nd.label} — ${nd.coordinated_posts}/${nd.posts} posts coordinated${nd.listed ? ` — ${nd.listed}` : ""}`}</title></circle>
            <text x={tx} y={ty} textAnchor={anchor} fontSize={14} fontWeight={600} fill="#0f172a" className="hover:fill-[#2457f5]">{label}</text>
          </g>
        );
      })}
    </svg>
  );
}

function Header({ data }: { data: Coord }) {
  const strong = data.edges.filter((e) => e.strong).length;
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-1 border-b border-line bg-panel px-5 py-2.5 text-[13px]">
      <span><b className="num text-[17px]">{data.nodes.length}</b> coordinated accounts</span>
      <span><b className="num text-[17px]">{data.communities.length}</b> groups</span>
      <span><b className="num text-[17px]">{strong}</b> strong links <span className="text-muted">(≥ 2 shared actions)</span></span>
      <span title={data.method[1]}>window <b className="num text-[17px]">{data.window_s}s</b> <span className="text-muted">learnt from {data.n_delays} re-share delays</span></span>
      <details className="relative ml-auto">
        <summary className="cursor-pointer text-accent">How is this computed?</summary>
        <ul className="absolute right-0 z-20 mt-2 w-[520px] list-disc space-y-1 rounded-md border border-line bg-panel p-3 pl-7 text-[12.5px] shadow-lg">
          {data.method.map((m) => <li key={m}>{m}</li>)}
          <li>Coordinated is not the same as fake: always read what the group shares before concluding.</li>
        </ul>
      </details>
    </div>
  );
}

function Barcode({ data, members, onNode }: { data: Coord; members: string[]; onNode: (id: string) => void }) {
  const rows = members.slice(0, 10);
  const lab = new Map(data.nodes.map((n) => [n.id, n]));
  const all = rows.flatMap((id) => data.barcode[id] ?? []);
  const coordTs = all.filter((p) => p.c).map((p) => +new Date(p.ts));
  if (!rows.length || !coordTs.length) return null;
  const pad = Math.max(3600e3, (Math.max(...coordTs) - Math.min(...coordTs)) * 0.05);
  const t0 = Math.min(...coordTs) - pad, t1 = Math.max(...coordTs) + pad;
  const pct = (t: number) => ((t - t0) / (t1 - t0)) * 100;
  const ticks = Array.from({ length: 4 }, (_, k) => t0 + ((t1 - t0) * (k + 0.5)) / 4);
  return (
    <div>
      <div className="mb-1 text-[11.5px] font-semibold uppercase text-muted">When they post</div>
      <div className="grid grid-cols-[150px_1fr] gap-x-2 gap-y-[3px]">
        {rows.map((id) => (
          <div key={id} className="contents">
            <button onClick={() => onNode(id)} className="num truncate text-left text-[12px] leading-[18px] text-accent hover:underline">{lab.get(id)?.label ?? id.slice(0, 8)}</button>
            <div className="relative h-[18px] rounded-sm bg-panel-2">
              {(data.barcode[id] ?? []).map((p, k) => {
                const t = +new Date(p.ts);
                if (t < t0 || t > t1) return null;
                return <span key={k} className={`absolute ${p.c ? "top-0 h-full w-[3px] bg-sev-priority" : "top-[5px] h-[8px] w-px bg-[#94a3b8]"}`} style={{ left: `${pct(t)}%` }} />;
              })}
            </div>
          </div>
        ))}
        <div />
        <div className="relative h-4">
          {ticks.map((t) => <span key={t} className="num absolute -translate-x-1/2 whitespace-nowrap text-[10.5px] text-muted" style={{ left: `${pct(t)}%` }}>{new Date(t).toISOString().slice(5, 16).replace("T", " ")}</span>)}
        </div>
      </div>
    </div>
  );
}
