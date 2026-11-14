"use client";
import { useMemo, useState } from "react";
import { useOps } from "@/lib/store";
import { useView } from "@/lib/useView";
import { STANCE, getThemes, type Stance, type Theme, type Themes as ThemesT } from "@/lib/views";
import { Empty, PlatformBadge } from "@/components/ui/kit";

/** Une couleur par thème, la même dans la carte, le flux et la matrice de cet onglet. */
const PAL = ["#4f46e5", "#0d9488", "#c026d3", "#ea580c", "#0284c7", "#65a30d", "#be123c", "#a16207", "#7c3aed", "#0f766e", "#475569", "#db2777"];
const SRC: Record<string, { label: string; help: string }> = {
  listed: { label: "Listed networks", help: "Documented influence networks (Pravda…) or state media" },
  automated: { label: "Automated", help: "Bot-like volume (≥ 72 posts/day) or declared bot" },
  media: { label: "News sites", help: "Web articles from news outlets" },
  social: { label: "Other accounts", help: "Individual social accounts" },
};
const LANG: Record<string, string> = { fr: "French", en: "English", ru: "Russian", de: "German", it: "Italian", es: "Spanish", pl: "Polish" };

export default function Themes({ slug }: { slug: string }) {
  const { data } = useView(() => getThemes(slug), [slug]);
  const [sel, setSel] = useState<number | null>(null);
  const color = useMemo(() => new Map((data?.themes ?? []).map((t, k) => [t.id, PAL[k % PAL.length]])), [data]);
  if (!data) return <div className="p-8"><Empty text="Grouping every post into themes (first load takes ~30 s)…" /></div>;
  if (!data.themes.length) return <div className="p-8"><Empty text="Not enough posts to form themes yet." /></div>;
  const theme = data.themes.find((t) => t.id === sel) ?? null;
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[1440px] space-y-5 p-5">
        <div className="flex items-baseline gap-4">
          <h2 className="text-[18px] font-semibold">{data.k} themes across {data.n_items.toLocaleString("en-US")} posts</h2>
          <span className="text-[13px] text-muted">What is being pushed, by whom, in which language — click a theme.</span>
          <details className="relative ml-auto text-[13px]">
            <summary className="cursor-pointer text-accent">How are themes built?</summary>
            <ul className="absolute right-0 z-20 mt-2 w-[520px] list-disc space-y-1 rounded-md border border-line bg-panel p-3 pl-7 text-[12.5px] shadow-lg">
              {data.method.map((m) => <li key={m}>{m}</li>)}
            </ul>
          </details>
        </div>
        <div className="grid grid-cols-[1fr_420px] gap-5">
          <section className="rounded-md border border-line bg-panel p-3">
            <Treemap themes={data.themes} color={color} sel={sel} onSel={setSel} />
          </section>
          <aside className="max-h-[520px] overflow-y-auto rounded-md border border-line bg-panel">
            {theme ? <Detail t={theme} c={color.get(theme.id)!} onClose={() => setSel(null)} /> : <Pressure themes={data.themes} color={color} onSel={setSel} />}
          </aside>
        </div>
        <section className="rounded-md border border-line bg-panel p-4">
          <div className="mb-2 flex items-baseline gap-3"><b className="text-[14px]">Themes over time</b><span className="text-[12.5px] text-muted">posts per day, stacked · hover a band</span></div>
          <Stream data={data} color={color} sel={sel} onSel={setSel} />
        </section>
        <section className="rounded-md border border-line bg-panel p-4">
          <div className="mb-2 flex items-baseline gap-3"><b className="text-[14px]">Who pushes which theme</b><span className="text-[12.5px] text-muted">share of each theme’s posts · darker = larger share</span></div>
          <Matrix themes={data.themes} color={color} sel={sel} onSel={setSel} />
        </section>
      </div>
    </div>
  );
}

/* ---------- Carte en mosaïque (squarified) ---------- */
type Rect = { x: number; y: number; w: number; h: number };
function squarify(values: number[], r: Rect): Rect[] {
  const out: Rect[] = new Array(values.length);
  const total = values.reduce((a, b) => a + b, 0) || 1;
  const area = values.map((v) => (v / total) * r.w * r.h);
  let idx = 0, box = { ...r };
  const worst = (row: number[], side: number) => { const s = row.reduce((a, b) => a + b, 0); return Math.max(...row.map((a) => Math.max((side * side * a) / (s * s), (s * s) / (side * side * a)))); };
  while (idx < area.length) {
    const side = Math.min(box.w, box.h);
    const row = [area[idx]];
    let j = idx + 1;
    while (j < area.length && worst([...row, area[j]], side) <= worst(row, side)) row.push(area[j++]);
    const s = row.reduce((a, b) => a + b, 0);
    const thick = s / side;
    let off = 0;
    row.forEach((a, k) => {
      const len = a / thick;
      out[idx + k] = box.w >= box.h ? { x: box.x, y: box.y + off, w: thick, h: len } : { x: box.x + off, y: box.y, w: len, h: thick };
      off += len;
    });
    box = box.w >= box.h ? { x: box.x + thick, y: box.y, w: box.w - thick, h: box.h } : { x: box.x, y: box.y + thick, w: box.w, h: box.h - thick };
    idx = j;
  }
  return out;
}

function Treemap({ themes, color, sel, onSel }: { themes: Theme[]; color: Map<number, string>; sel: number | null; onSel: (k: number) => void }) {
  const W = 900, H = 500;
  const rects = squarify(themes.map((t) => t.items), { x: 0, y: 0, w: W, h: H });
  return (
    <div className="relative w-full" style={{ aspectRatio: `${W}/${H}` }}>
      {themes.map((t, k) => {
        const r = rects[k];
        const pressure = ((t.sources.listed ?? 0) + (t.sources.automated ?? 0)) / t.items;
        const small = r.w < 150 || r.h < 90;
        return (
          <button key={t.id} onClick={() => onSel(t.id)} title={`${t.name} — ${t.framing}`}
            className={`absolute overflow-hidden border-2 border-panel p-2 text-left text-white transition-opacity ${sel !== null && sel !== t.id ? "opacity-40" : ""}`}
            style={{ left: `${(r.x / W) * 100}%`, top: `${(r.y / H) * 100}%`, width: `${(r.w / W) * 100}%`, height: `${(r.h / H) * 100}%`, background: color.get(t.id) }}>
            <div className={`font-semibold leading-tight ${small ? "text-[12px]" : "text-[15px]"}`}>{t.name}</div>
            <div className="num mt-0.5 text-[11.5px] text-white/85">{t.items} posts · {t.accounts} accounts</div>
            {!small && <div className="mt-1 line-clamp-3 text-[12px] leading-snug text-white/90">{t.framing}</div>}
            {pressure >= 0.05 && (
              <span className="num absolute bottom-1.5 right-1.5 rounded bg-white/95 px-1.5 text-[11px] font-semibold text-sev-priority"
                title="Share of posts from listed networks or automated accounts">★⚙ {Math.round(pressure * 100)}%</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/** Panneau par défaut : thèmes classés par part de sources listées ou automatisées. */
function Pressure({ themes, color, onSel }: { themes: Theme[]; color: Map<number, string>; onSel: (k: number) => void }) {
  const rows = [...themes].map((t) => ({ t, l: (t.sources.listed ?? 0) / t.items, a: (t.sources.automated ?? 0) / t.items }))
    .sort((x, y) => y.l + y.a - (x.l + x.a));
  return (
    <div className="p-4">
      <div className="text-[14px] font-semibold">Which themes are pushed by networks and bots?</div>
      <p className="mt-0.5 text-[12.5px] text-muted">Share of each theme coming from <span className="font-semibold text-sev-priority">listed networks</span> and <span className="font-semibold text-sev-review">automated accounts</span>.</p>
      <ul className="mt-3 space-y-2">
        {rows.map(({ t, l, a }) => (
          <li key={t.id}>
            <button onClick={() => onSel(t.id)} className="w-full text-left">
              <div className="flex items-center gap-2 text-[13px]"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: color.get(t.id) }} /><span className="flex-1 truncate">{t.name}</span><span className="num text-[12px] text-muted">{Math.round((l + a) * 100)}%</span></div>
              <div className="mt-1 flex h-2 overflow-hidden rounded-full bg-line">
                <span style={{ width: `${l * 100}%` }} className="bg-sev-priority" /><span style={{ width: `${a * 100}%` }} className="bg-sev-review" />
              </div>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Detail({ t, c, onClose }: { t: Theme; c: string; onClose: () => void }) {
  const { openAccount, openStory } = useOps();
  const st = Object.entries(t.stance).filter(([s]) => s !== "unclassified") as [Stance, number][];
  return (
    <div>
      <div className="border-b border-line p-4" style={{ borderTop: `4px solid ${c}` }}>
        <div className="flex items-start gap-2"><div className="flex-1 text-[16px] font-semibold leading-snug">{t.name}</div>
          <button onClick={onClose} className="text-[12px] text-muted hover:text-text">All themes ✕</button></div>
        <p className="mt-1.5 text-[13px] leading-relaxed">{t.framing}</p>
        <div className="mt-2 flex flex-wrap gap-1.5">{t.keywords.map((k) => <span key={k} className="rounded bg-panel-2 px-1.5 text-[12px] text-muted">{k}</span>)}</div>
        <div className="num mt-2 text-[12.5px] text-muted">{t.items} posts · {t.accounts} accounts · {t.narratives.length} narratives
          {st.length > 0 && <> · {st.map(([s, n]) => `${STANCE[s]?.label ?? s} ${n}`).join(" · ")}</>}</div>
        {t.narratives.length > 0 && <button onClick={() => openStory(t.narratives[0])} className="mt-1 text-[12.5px] text-accent hover:underline">Open its largest narrative →</button>}
      </div>
      <div className="border-b border-line p-4">
        <div className="text-[12.5px] font-semibold text-muted">TOP ACCOUNTS</div>
        <ul className="mt-1">
          {t.top_accounts.map((a) => (
            <li key={a.id}><button onClick={() => openAccount(a.id)} className="flex w-full items-center gap-2 border-b border-line py-1 text-left text-[13px] hover:bg-panel-2">
              <span className="num flex-1 truncate text-accent">{a.label}</span>
              {a.source !== "social" && a.source !== "media" && <span className={`rounded px-1.5 text-[11px] font-semibold ${a.source === "listed" ? "bg-sev-priority/15 text-sev-priority" : "bg-sev-review/15 text-sev-review"}`}>{SRC[a.source].label}</span>}
              <span className="num text-[12px] text-muted">{a.posts}</span></button></li>
          ))}
        </ul>
      </div>
      <div className="p-4">
        <div className="text-[12.5px] font-semibold text-muted">MOST TYPICAL POSTS</div>
        <ul className="mt-2 space-y-2">
          {t.examples.map((e) => (
            <li key={e.uid} className="rounded-md border border-line p-2 text-[12.5px]">
              <div className="flex items-center gap-2 text-[11.5px] text-muted"><PlatformBadge p={e.platform} /><span className="num">{e.ts.slice(0, 10)}</span>
                {e.url && <a href={e.url} target="_blank" rel="noreferrer" className="ml-auto text-accent hover:underline">source ↗</a>}</div>
              <div className="mt-1 line-clamp-3 italic">“{e.text}”</div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

/* ---------- Flux des thèmes dans le temps (aires empilées) ---------- */
function Stream({ data, color, sel, onSel }: { data: ThemesT; color: Map<number, string>; sel: number | null; onSel: (k: number) => void }) {
  const [hover, setHover] = useState<{ t: Theme; d: number } | null>(null);
  const W = 1300, H = 230, n = data.days.length;
  const totals = data.days.map((_, d) => data.themes.reduce((a, t) => a + t.series[d], 0));
  const max = Math.max(1, ...totals);
  const x = (d: number) => (n <= 1 ? 0 : (d / (n - 1)) * W);
  const y = (v: number) => H - (v / max) * (H - 10);
  const base = new Array(n).fill(0);
  const bands = data.themes.map((t) => {
    const lo = [...base];
    t.series.forEach((v, d) => { base[d] += v; });
    const hi = [...base];
    const path = "M" + hi.map((v, d) => `${x(d)},${y(v)}`).join("L") + "L" + lo.map((v, d) => `${x(d)},${y(v)}`).reverse().join("L") + "Z";
    return { t, path };
  });
  const labelDays = data.days.map((d, k) => [d, k] as const).filter((_, k) => k % Math.max(1, Math.ceil(n / 10)) === 0);
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="h-[230px] w-full"
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => { const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect(); const d = Math.round(((e.clientX - r.left) / r.width) * (n - 1)); if (hover) setHover({ t: hover.t, d }); }}>
        {bands.map(({ t, path }) => (
          <path key={t.id} d={path} fill={color.get(t.id)} opacity={sel === null || sel === t.id ? 0.88 : 0.15} stroke="#fff" strokeWidth={0.5}
            onMouseEnter={() => setHover((h) => ({ t, d: h?.d ?? 0 }))} onClick={() => onSel(t.id)} className="cursor-pointer" />
        ))}
      </svg>
      <div className="relative h-5">
        {labelDays.map(([d, k]) => <span key={d} className="num absolute -translate-x-1/2 text-[10.5px] text-muted" style={{ left: `${(x(k) / W) * 100}%` }}>{d.slice(5)}</span>)}
      </div>
      {hover && (
        <div className="pointer-events-none absolute right-2 top-2 rounded-md border border-line bg-panel px-3 py-2 text-[12.5px] shadow">
          <div className="flex items-center gap-2 font-semibold"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: color.get(hover.t.id) }} />{hover.t.name}</div>
          <div className="num text-muted">{data.days[hover.d]} · {hover.t.series[hover.d] ?? 0} posts</div>
        </div>
      )}
    </div>
  );
}

/* ---------- Matrice thème × type de source / langue / plateforme ---------- */
function Matrix({ themes, color, sel, onSel }: { themes: Theme[]; color: Map<number, string>; sel: number | null; onSel: (k: number) => void }) {
  const langs = Object.entries(themes.reduce<Record<string, number>>((a, t) => { for (const [l, n] of Object.entries(t.langs)) if (l !== "?") a[l] = (a[l] ?? 0) + n; return a; }, {}))
    .sort((a, b) => b[1] - a[1]).slice(0, 7).map(([l]) => l);
  const plats = Object.entries(themes.reduce<Record<string, number>>((a, t) => { for (const [p, n] of Object.entries(t.platforms)) a[p] = (a[p] ?? 0) + n; return a; }, {}))
    .sort((a, b) => b[1] - a[1]).map(([p]) => p);
  const cell = (key: string, n: number, tot: number, hue: string) => {
    const s = tot ? n / tot : 0;
    return (
      <td key={key} className="num px-1 py-1 text-center text-[12px]" title={`${n} posts (${Math.round(s * 100)}%)`}>
        <div className="mx-auto rounded py-1" style={{ background: s ? `color-mix(in srgb, ${hue} ${Math.round(8 + s * 82)}%, white)` : "transparent", color: s > 0.45 ? "white" : undefined }}>
          {s ? (s < 0.005 ? "<1%" : `${Math.round(s * 100)}%`) : "·"}
        </div>
      </td>
    );
  };
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-separate border-spacing-0 text-[12.5px]">
        <thead className="text-[11.5px] text-muted">
          <tr>
            <th />
            <th colSpan={4} className="border-b border-line pb-1 font-semibold">WHO (source type)</th>
            <th colSpan={langs.length} className="border-b border-l border-line pb-1 font-semibold">LANGUAGE</th>
            <th colSpan={plats.length} className="border-b border-l border-line pb-1 font-semibold">PLATFORM</th>
          </tr>
          <tr>
            <th className="py-1 text-left font-medium">Theme</th>
            {Object.keys(SRC).map((s) => <th key={s} className="px-1 font-medium" title={SRC[s].help}>{SRC[s].label}</th>)}
            {langs.map((l, k) => <th key={l} className={`px-1 font-medium ${k === 0 ? "border-l border-line" : ""}`}>{LANG[l] ?? l}</th>)}
            {plats.map((p, k) => <th key={p} className={`px-1 font-medium ${k === 0 ? "border-l border-line" : ""}`}><PlatformBadge p={p} /></th>)}
          </tr>
        </thead>
        <tbody>
          {themes.map((t) => (
            <tr key={t.id} onClick={() => onSel(t.id)} className={`cursor-pointer ${sel === t.id ? "bg-[#eef3fd]" : "hover:bg-panel-2"}`}>
              <td className="max-w-[260px] py-1 pr-2"><span className="flex items-center gap-2"><span className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: color.get(t.id) }} /><span className="truncate">{t.name}</span><span className="num ml-auto text-[11.5px] text-muted">{t.items}</span></span></td>
              {cell("s-listed", t.sources.listed ?? 0, t.items, "#dc2626")}
              {cell("s-auto", t.sources.automated ?? 0, t.items, "#ea7a00")}
              {cell("s-media", t.sources.media ?? 0, t.items, "#475569")}
              {cell("s-social", t.sources.social ?? 0, t.items, "#475569")}
              {langs.map((l) => cell("l-" + l, t.langs[l] ?? 0, t.items, "#2457f5"))}
              {plats.map((p) => cell("p-" + p, t.platforms[p] ?? 0, t.items, "#0f1b3d"))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
