"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import Graph from "graphology";
import type Sigma from "sigma";
import { passes, useOps } from "@/lib/store";
import { useView } from "@/lib/useView";
import { STANCE, getNetwork, type Account, type Stance } from "@/lib/views";
import { Empty, FlagChips, PlatformBadge, SeverityBadge, StanceChip } from "@/components/ui/kit";

const css = (v: string) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const riskVar = (r: string) => (r === "high" ? "--sev-priority" : r === "medium" ? "--sev-review" : "--sev-organic");

/** Graphe en étoile : hubs = histoires, rayons = comptes, ponts = comptes présents dans plusieurs histoires. */
interface Hub { id: string; title: string; stance: Stance; level: string; accounts: string[] }
interface Star { hubs: Hub[]; accounts: Account[]; links: { account: string; story: string; stance: Stance }[] }

type HoverT = { kind: "account"; a: Account; x: number; y: number } | { kind: "story"; h: Hub; x: number; y: number };

export default function NetworkView({ slug }: { slug: string }) {
  const { data } = useView(() => getNetwork(slug), [slug]);
  const { filters, openAccount, openStory } = useOps();
  const [sel, setSel] = useState<string | null>(null);
  const [hover, setHover] = useState<HoverT | null>(null);
  const [showSmall, setShowSmall] = useState(false);
  const [until, setUntil] = useState<number | null>(null);  // replay : n'afficher que ce qui existait à cette date
  const [playing, setPlaying] = useState(false);

  const star = useMemo<Star | null>(() => {
    if (!data) return null;
    const accounts = data.nodes.filter((n) => passes(filters, { platform: n.platform }));
    const hubs: Hub[] = Object.entries(data.stories)
      .filter(([, s]) => passes(filters, { stance: s.stance, level: s.level }))
      .map(([id, s]) => ({ id, title: s.title, stance: s.stance, level: s.level, accounts: accounts.filter((a) => a.stories.includes(id)).map((a) => a.id) }))
      .filter((h) => h.accounts.length >= (showSmall ? 2 : 3))  // par défaut : narratifs portés par ≥ 3 comptes
      .sort((a, b) => b.accounts.length - a.accounts.length);
    const hubIds = new Set(hubs.map((h) => h.id));
    const used = accounts.filter((a) => a.stories.some((s) => hubIds.has(s)));
    const links = used.flatMap((a) => a.stories.filter((s) => hubIds.has(s)).map((s) => ({ account: a.id, story: s, stance: data.stories[s].stance })));
    return { hubs, accounts: used, links };
  }, [data, filters, showSmall]);
  // Reconstruit seulement si la structure change (la vue ne saute pas à chaque donnée live)
  const sig = star ? star.hubs.map((h) => h.id + ":" + h.accounts.length).join(",") + "|" + star.accounts.length : "";
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const stable = useMemo(() => star, [sig]);

  const span = useMemo(() => {
    const ts = (stable?.accounts ?? []).map((a) => +new Date(a.first_ts));
    return ts.length ? [Math.min(...ts), Math.max(...ts)] as const : null;
  }, [stable]);
  useEffect(() => {
    if (!playing || !span) return;
    const step = (span[1] - span[0]) / 60;
    const t = setInterval(() => setUntil((u) => {
      const next = (u ?? span[0]) + step;
      if (next >= span[1]) { setPlaying(false); return null; }
      return next;
    }), 120);
    return () => clearInterval(t);
  }, [playing, span]);

  if (!stable) return <div className="p-8"><Empty text="Loading the network…" /></div>;
  if (!stable.hubs.length) return <div className="p-8"><Empty text="No narrative with at least two accounts matches the filters." /></div>;

  const hubIds = new Set(stable.hubs.map((h) => h.id));
  const selHub = stable.hubs.find((h) => "s:" + h.id === sel);
  const selAcc = stable.accounts.find((a) => "a:" + a.id === sel);
  const bridges = stable.accounts.filter((a) => a.stories.filter((s) => hubIds.has(s)).length >= 2);
  const rows = selHub ? stable.accounts.filter((a) => selHub.accounts.includes(a.id))
    : [...stable.accounts].sort((a, b) => b.stories.length - a.stories.length || b.items - a.items);

  return (
    <div className="grid h-full min-h-0 grid-cols-[1fr_400px]">
      <main className="relative min-h-0 bg-panel">
        <StarGraph star={stable} until={until} selected={sel} onSelect={setSel} onHover={setHover}
          onOpen={(id) => (id.startsWith("s:") ? openStory(id.slice(2)) : openAccount(id.slice(2)))} />
        {span && (
          <div className="absolute bottom-4 left-4 right-20 flex items-center gap-3 rounded-md border border-line bg-panel px-3 py-2 shadow-sm">
            <button onClick={() => { if (!playing && until === null) setUntil(span[0]); setPlaying(!playing); }}
              className="rounded-md bg-accent px-3 py-1 text-[12.5px] font-medium text-white">{playing ? "Pause" : "▶ Replay"}</button>
            <input type="range" min={span[0]} max={span[1]} value={until ?? span[1]} className="flex-1 accent-[var(--accent)]"
              onChange={(e) => { setPlaying(false); setUntil(+e.target.value >= span[1] ? null : +e.target.value); }} />
            <span className="num w-36 text-right text-[12.5px] text-muted">{until ? new Date(until).toISOString().slice(5, 16).replace("T", " ") + "Z" : "now (all)"}</span>
          </div>
        )}
        <details className="absolute left-4 top-4 w-[290px] rounded-md border border-line bg-panel p-3 text-[12.5px] shadow-sm">
          <summary className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px]">
            <b className="text-[13px]">Legend ▾</b>
            <Sw c={STANCE.promotes.color} t="repeats claim" /><Sw c={STANCE.debunks.color} t="debunks claim" /><Sw c="var(--sev-priority)" t="listed source" />
          </summary>
          <div className="mt-2 grid grid-cols-[18px_1fr] items-center gap-x-2 gap-y-1.5">
            <span className="h-4 w-4 rounded-full" style={{ background: STANCE.promotes.color }} /><span><b>Big dot = narrative</b> (hub), colour = stance:</span>
            <span /><span className="flex flex-wrap gap-x-3"><Sw c={STANCE.promotes.color} t="repeats claim" /><Sw c={STANCE.debunks.color} t="debunks claim" /><Sw c={STANCE.neutral.color} t="neutral" /></span>
            <span className="h-2.5 w-2.5 justify-self-center rounded-full" style={{ background: "var(--sev-organic)" }} /><span><b>Small dot = account</b>, colour = risk:</span>
            <span /><span className="flex flex-wrap gap-x-3"><Sw c="var(--sev-priority)" t="listed / bot" /><Sw c="var(--sev-review)" t="< 30 days" /><Sw c="var(--sev-organic)" t="none" /></span>
            <span className="h-[3px] w-4 rounded" style={{ background: "var(--muted)" }} /><span>Line = the account published in that narrative.</span>
          </div>
          <p className="mt-2 text-muted">Accounts <b className="text-text">between two hubs</b> took part in several narratives: they are the bridges to look at first.</p>
          <div className="mt-1 text-[11.5px] text-faint">Hover for details · click to highlight · double-click to open</div>
          <label className="mt-2 flex items-center gap-2 text-[12.5px]"><input type="checkbox" checked={showSmall} onChange={(e) => setShowSmall(e.target.checked)} />Include narratives with only 2 accounts</label>
        </details>
        {hover && (
          <div className="pointer-events-none absolute z-10 w-[300px] rounded-md border border-line-strong bg-panel p-3 text-[12.5px] shadow-[0_6px_20px_rgba(20,30,50,.15)]"
            style={{ left: hover.x + 16, top: hover.y + 16 }}>
            {hover.kind === "story" ? (
              <>
                <div className="flex items-center gap-2"><SeverityBadge level={hover.h.level} size="sm" /><StanceChip stance={hover.h.stance} /></div>
                <div className="mt-1.5 font-medium leading-snug">{hover.h.title}</div>
                <div className="num mt-1 text-muted">{hover.h.accounts.length} accounts · double-click to open the narrative</div>
              </>
            ) : (
              <>
                <div className="flex items-center gap-2"><PlatformBadge p={hover.a.platform} /><span className="num font-semibold">{hover.a.label}</span></div>
                <div className="mt-1.5"><FlagChips flags={hover.a.flags} /></div>
                <div className="num mt-1.5 text-muted">{hover.a.items} posts · in {hover.a.stories.length} {hover.a.stories.length > 1 ? "narratives (bridge)" : "narrative"}</div>
              </>
            )}
          </div>
        )}
      </main>

      <aside className="flex min-h-0 flex-col border-l border-line bg-panel">
        <div className="border-b border-line p-4">
          {selHub ? (
            <>
              <div className="flex items-center gap-2"><SeverityBadge level={selHub.level} size="sm" /><StanceChip stance={selHub.stance} />
                <button onClick={() => setSel(null)} className="ml-auto text-[12px] text-muted hover:text-text">Clear ✕</button></div>
              <div className="mt-2 text-[14px] font-semibold leading-snug">{selHub.title}</div>
              <button onClick={() => openStory(selHub.id)} className="mt-2 text-[12.5px] text-accent hover:underline">Open the narrative →</button>
            </>
          ) : selAcc ? (
            <>
              <div className="flex items-center gap-2"><PlatformBadge p={selAcc.platform} /><span className="num text-[14px] font-semibold">{selAcc.label}</span>
                <button onClick={() => setSel(null)} className="ml-auto text-[12px] text-muted hover:text-text">Clear ✕</button></div>
              <div className="mt-2"><FlagChips flags={selAcc.flags} /></div>
              <button onClick={() => openAccount(selAcc.id)} className="mt-2 text-[12.5px] text-accent hover:underline">Open the account →</button>
            </>
          ) : (
            <>
              <div className="text-[13px] font-semibold">{stable.hubs.length} narratives · {stable.accounts.length} accounts · {bridges.length} bridges</div>
              <p className="mt-1 text-[12.5px] text-muted">Bridges are accounts present in several narratives — the first ones to check for coordinated behaviour.</p>
            </>
          )}
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          <table className="w-full text-[12.5px]">
            <thead className="sticky top-0 bg-panel text-left text-[12px] text-muted">
              <tr className="border-b border-line"><th className="px-3 py-2 font-medium">Account</th><th className="font-medium">Flags</th><th className="px-3 text-right font-medium">Narratives</th></tr>
            </thead>
            <tbody>
              {rows.map((a) => (
                <tr key={a.id} onClick={() => setSel("a:" + a.id)} onDoubleClick={() => openAccount(a.id)}
                  className={`cursor-pointer border-b border-line ${sel === "a:" + a.id ? "bg-[#eef3fd]" : "hover:bg-panel-2"}`}>
                  <td className="px-3 py-1.5"><span className="flex items-center gap-2"><span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: `var(${riskVar(a.risk)})` }} /><span className="num truncate">{a.label}</span></span></td>
                  <td><FlagChips flags={a.flags.filter((f) => f.risk !== "low")} /></td>
                  <td className="num px-3 text-right">{a.stories.length}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </aside>
    </div>
  );
}

function Sw({ c, t }: { c: string; t: string }) {
  return <span className="inline-flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-full" style={{ background: c }} />{t}</span>;
}

/** Petit hash déterministe (positions stables d'un chargement à l'autre). */
const h01 = (s: string) => { let h = 2166136261; for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619); return ((h >>> 0) % 1000) / 1000; };

/** Mise en page déterministe : hubs sur une grille, comptes en couronne autour de leur hub, ponts entre leurs hubs. */
function layout(star: Star) {
  const pos = new Map<string, { x: number; y: number }>();
  const n = star.hubs.length;
  const cols = Math.max(1, Math.ceil(Math.sqrt(n * 1.5)));
  const rowsN = Math.ceil(n / cols);
  const cellX = 620, cellY = 560;  // les couronnes occupent l'essentiel de la cellule : de vraies « étoiles »
  star.hubs.forEach((h, i) => {
    const r = Math.floor(i / cols), c = i % cols;
    pos.set("s:" + h.id, { x: (c - (cols - 1) / 2) * cellX + (r % 2 ? cellX / 2 : 0), y: (r - (rowsN - 1) / 2) * cellY });
  });
  const hubSet = new Set(star.hubs.map((h) => h.id));
  const byId = new Map(star.accounts.map((a) => [a.id, a]));
  for (const h of star.hubs) {
    const c = pos.get("s:" + h.id)!;
    const own = h.accounts.filter((id) => (byId.get(id)?.stories.filter((s) => hubSet.has(s)).length ?? 0) === 1);
    const R = 150 + Math.min(110, own.length * 8);
    own.forEach((id, k) => {
      const ang = (k / own.length) * Math.PI * 2 + h01(h.id) * Math.PI;
      pos.set("a:" + id, { x: c.x + Math.cos(ang) * R, y: c.y + Math.sin(ang) * R });
    });
  }
  for (const a of star.accounts) {
    const hs = a.stories.filter((s) => hubSet.has(s));
    if (hs.length < 2) continue;
    const pts = hs.map((s) => pos.get("s:" + s)!);
    const x = pts.reduce((t, p) => t + p.x, 0) / pts.length, y = pts.reduce((t, p) => t + p.y, 0) / pts.length;
    pos.set("a:" + a.id, { x: x + (h01(a.id) - 0.5) * 140, y: y + (h01(a.id + "y") - 0.5) * 140 });
  }
  return pos;
}

function StarGraph({ star, until, selected, onSelect, onHover, onOpen }: {
  star: Star; until: number | null; selected: string | null; onSelect: (id: string | null) => void;
  onHover: (h: HoverT | null) => void; onOpen: (id: string) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const sigmaRef = useRef<Sigma | null>(null);
  const graphRef = useRef<Graph | null>(null);
  const cameraRef = useRef<{ x: number; y: number; ratio: number; angle: number } | null>(null);
  const starRef = useRef(star);
  useEffect(() => { starRef.current = star; }, [star]);

  useEffect(() => {
    let disposed = false;
    (async () => {
      const { default: SigmaCtor } = await import("sigma");
      if (disposed || !ref.current) return;
      const g = new Graph({ type: "undirected" });
      graphRef.current = g;
      const pos = layout(star);
      for (const h of star.hubs) {
        g.addNode("s:" + h.id, { ...pos.get("s:" + h.id)!, size: 13 + Math.min(10, h.accounts.length), color: css(`--st-${h.stance}`) || css("--st-neutral"),
          label: h.title.length > 34 ? h.title.slice(0, 32).trim() + "…" : h.title, forceLabel: true, zIndex: 3 });
      }
      for (const a of star.accounts) {
        const p = pos.get("a:" + a.id);
        if (!p) continue;
        g.addNode("a:" + a.id, { ...p, size: 4.5 + Math.min(5, Math.sqrt(a.items) * 1.6), color: css(riskVar(a.risk)), label: a.label,
          forceLabel: a.stories.length > 1 || a.risk !== "none", zIndex: a.stories.length > 1 ? 2 : 1 });
      }
      for (const l of star.links) {
        const s = "s:" + l.story, t = "a:" + l.account;
        if (g.hasNode(s) && g.hasNode(t) && !g.hasEdge(s, t)) g.addEdge(s, t, { size: 1.6, color: css(`--st-${l.stance}`) || css("--st-neutral") });
      }
      const sigma = new SigmaCtor(g, ref.current, {
        allowInvalidContainer: true, labelSize: 11.5, labelWeight: "500", labelColor: { color: css("--text") },
        labelDensity: 0.6, labelRenderedSizeThreshold: 7, stagePadding: 50, zIndex: true, minEdgeThickness: 1.2,
      });
      sigmaRef.current = sigma;
      if (cameraRef.current) sigma.getCamera().setState(cameraRef.current);  // garde le zoom de l'utilisateur
      sigma.getCamera().on("updated", (st) => { cameraRef.current = st; });
      sigma.on("enterNode", ({ node }) => {
        const p = sigma.graphToViewport(g.getNodeAttributes(node) as { x: number; y: number });
        const S = starRef.current;
        if (node.startsWith("s:")) { const h = S.hubs.find((x) => "s:" + x.id === node); if (h) onHover({ kind: "story", h, x: p.x, y: p.y }); }
        else { const a = S.accounts.find((x) => "a:" + x.id === node); if (a) onHover({ kind: "account", a, x: p.x, y: p.y }); }
      });
      sigma.on("leaveNode", () => onHover(null));
      sigma.on("clickNode", ({ node }) => onSelect(node));
      sigma.on("doubleClickNode", ({ node, event }) => { event.preventSigmaDefault(); onOpen(node); });
      sigma.on("clickStage", () => onSelect(null));
    })();
    return () => { disposed = true; sigmaRef.current?.kill(); sigmaRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [star]);

  useEffect(() => {
    const sigma = sigmaRef.current, g = graphRef.current;
    if (!sigma || !g) return;
    const nb = new Set(selected && g.hasNode(selected) ? [selected, ...g.neighbors(selected)] : []);
    // Replay : un compte apparaît à sa première publication ; un hub dès qu'un de ses comptes est visible
    const born = new Map(star.accounts.map((a) => ["a:" + a.id, +new Date(a.first_ts)]));
    const visible = (n: string) => {
      if (until === null) return true;
      if (n.startsWith("a:")) return (born.get(n) ?? 0) <= until;
      return g.neighbors(n).some((m) => (born.get(m) ?? Infinity) <= until);
    };
    sigma.setSetting("nodeReducer", (n, d) => {
      if (!visible(n)) return { ...d, hidden: true };
      if (!selected) return d;
      return nb.has(n) ? { ...d, zIndex: 4, forceLabel: true, highlighted: n === selected } : { ...d, color: "#e3e7ec", label: "", zIndex: 0 };
    });
    sigma.setSetting("edgeReducer", (e, d) => {
      const [a, b] = g.extremities(e);
      if (!visible(a) || !visible(b)) return { ...d, hidden: true };
      if (!selected) return d;
      return a === selected || b === selected ? { ...d, size: 2.6 } : { ...d, hidden: true };
    });
    sigma.refresh();
  }, [selected, until, star]);

  const zoom = (f: number | "fit") => {
    const cam = sigmaRef.current?.getCamera();
    if (!cam) return;
    if (f === "fit") cam.animatedReset({ duration: 300 });
    else cam.animate({ ratio: cam.ratio * f }, { duration: 250 });
  };
  return (
    <>
      <div ref={ref} className="absolute inset-0" />
      <div className="absolute bottom-4 right-4 flex flex-col overflow-hidden rounded-md border border-line bg-panel shadow-sm">
        <button onClick={() => zoom(0.7)} title="Zoom in" className="h-9 w-9 text-[18px] hover:bg-panel-2">+</button>
        <button onClick={() => zoom(1.4)} title="Zoom out" className="h-9 w-9 border-t border-line text-[18px] hover:bg-panel-2">−</button>
        <button onClick={() => zoom("fit")} title="Show everything" className="h-9 w-9 border-t border-line text-[13px] hover:bg-panel-2">⤢</button>
      </div>
    </>
  );
}
