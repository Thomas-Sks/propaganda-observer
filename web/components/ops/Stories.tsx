"use client";
import { useMemo, useState } from "react";
import { passes, useOps } from "@/lib/store";
import { useView } from "@/lib/useView";
import { PLATFORM_NAME, SEVERITY, STANCE, fmtTs, getStory, getSummary, type Account, type StoryDetail } from "@/lib/views";
import { Collapsible, Empty, FlagChips, PlatformBadge, Platforms, SeverityBadge, SignalBars, Sparkline, StanceChip } from "@/components/ui/kit";
import Investigation from "./Investigation";
import { HopList, fmtDelay } from "./Diffusion";

export default function Stories({ slug }: { slug: string }) {
  const { data } = useView(() => getSummary(slug), [slug]);
  const { filters, story, openStory } = useOps();
  const [q, setQ] = useState("");
  const range = useMemo(() => (data?.daily ?? []).map((d) => d.day), [data]);
  const list = (data?.stories ?? []).filter((s) => passes(filters, s) && s.title.toLowerCase().includes(q.toLowerCase()));
  const current = story ?? list[0]?.id ?? null;

  return (
    <div className="grid h-full min-h-0 grid-cols-[400px_1fr]">
      <aside className="flex min-h-0 flex-col border-r border-line bg-panel">
        <div className="border-b border-line p-3">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search narratives…"
            className="h-9 w-full rounded-md border border-line-strong bg-panel px-3 text-[13.5px] outline-none focus:border-accent" />
          <div className="mt-2 text-[12.5px] text-muted">{list.length} narratives · sorted by severity</div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {list.map((s) => (
            <button key={s.id} onClick={() => openStory(s.id)}
              style={{ borderLeft: `5px solid ${SEVERITY[s.level]?.color ?? "var(--line)"}` }}
              className={`block w-full border-b border-line px-4 py-3 text-left ${s.id === current ? "bg-[#e8eefe]" : "hover:bg-panel-2"}`}>
              <div className="flex items-center gap-2"><SeverityBadge level={s.level} size="sm" /><StanceChip stance={s.stance} /></div>
              <div className="mt-1.5 line-clamp-2 text-[14px] leading-snug">{s.title}</div>
              <div className="mt-1.5 flex items-center gap-2 text-[12px] text-muted">
                <Platforms list={s.platforms} />
                <span className="num ml-auto">{s.accounts} acc.</span>
                <Sparkline days={s.days} range={range} width={60} height={16} />
              </div>
            </button>
          ))}
          {!list.length && <div className="p-4"><Empty text="No narrative matches." /></div>}
        </div>
      </aside>
      <div className="min-h-0 overflow-y-auto">{current ? <Detail slug={slug} id={current} /> : <div className="p-8"><Empty text="Select a narrative" /></div>}</div>
    </div>
  );
}

function Detail({ slug, id }: { slug: string; id: string }) {
  const { data: d } = useView(() => getStory(slug, id), [slug, id]);
  const openAccount = useOps((s) => s.openAccount);
  const [flash, setFlash] = useState<string | null>(null);
  if (!d || d.id !== id) return <div className="p-8"><Empty text="Loading…" /></div>;
  // Une référence d'agent [P3]/[A1]/[S2] fait défiler jusqu'à la preuve et la surligne
  const goRef = (ref: string) => {
    setFlash(ref);
    const el = document.getElementById(`ev-${ref}`);
    el?.closest("details")?.setAttribute("open", "");
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
    setTimeout(() => setFlash(null), 2500);
  };
  const stanceSig = d.signals.find((s) => s.name.startsWith("stance_"));
  const span = (+new Date(d.last_ts) - +new Date(d.first_ts)) / 3.6e6;

  return (
    <div className="mx-auto max-w-[980px] space-y-4 p-6">
      {/* 1. Sévérité + position + titre (ordre Blackbird) */}
      <div className="flex flex-wrap items-center gap-3">
        <SeverityBadge level={d.level} /><StanceChip stance={d.stance} full /><Platforms list={d.platforms} />
        <span className="num ml-auto text-[12.5px] text-muted">score {d.score.toFixed(2)} · review ≥ 0.40 · priority ≥ 0.70</span>
      </div>
      <h1 className="text-[22px] font-semibold leading-snug">{d.title}</h1>
      <p className="text-[13.5px] text-muted">{SEVERITY[d.level]?.help}</p>

      {/* 2. Chiffres clés */}
      <div className="grid grid-cols-4 gap-px overflow-hidden rounded-md border border-line bg-line">
        {[["Accounts", d.accounts], ["Publications", d.items], ["First seen", fmtTs(d.first_ts)],
          ["Spread", span < 1 ? `${Math.round(span * 60)} min` : span < 48 ? `${span.toFixed(1)} h` : `${(span / 24).toFixed(1)} days`]].map(([k, v]) => (
          <div key={String(k)} className="bg-panel px-4 py-2.5"><div className="text-[12.5px] text-muted">{k}</div><div className="num mt-0.5 text-[15px] font-semibold">{v}</div></div>
        ))}
      </div>

      {/* 3. Position, avec la citation qui la justifie */}
      {stanceSig && (
        <blockquote className="rounded-md border-l-4 bg-panel px-4 py-3 text-[14px]" style={{ borderColor: STANCE[d.stance].color }}>
          <div className="text-[12.5px] font-semibold" style={{ color: STANCE[d.stance].color }}>{STANCE[d.stance].label} <span className="font-normal text-faint">· assessed by an LLM, quote below</span></div>
          <div className="mt-1 italic">{stanceSig.explanation.replace(/ \(LLM-assessed\)$/, "")}</div>
        </blockquote>
      )}

      {/* 4. Sections repliables */}
      <Collapsible title="AI investigation" hint="investigator ⇄ skeptic → judge, evidence-linked" defaultOpen>
        <Investigation slug={slug} storyId={id} onRef={goRef} />
      </Collapsible>

      <Collapsible title="Why this verdict" hint="each signal adds to the score · S1, S2… in order" defaultOpen>
        <ol>
          {d.signals.map((sg, k) => (
            <li key={sg.name} id={`ev-S${k + 1}`} className={`flex gap-3 rounded ${flash === `S${k + 1}` ? "bg-[#fff3c4]" : ""}`}>
              <span className="num w-7 pt-2 text-[11.5px] text-faint">S{k + 1}</span>
              <div className="flex-1"><SignalBars signals={[sg].map((x) => ({ ...x, name: x.name.replace("stance_", "stance:") }))} /></div>
            </li>
          ))}
        </ol>
      </Collapsible>

      <Collapsible title="How it spread" hint="one row per platform, same time axis" defaultOpen>
        <Spread d={d} />
        {d.diffusion && d.diffusion.entries.length > 1 && <CrossPlatform d={d} />}
      </Collapsible>

      <Collapsible title="Accounts involved" count={d.accounts_detail.length} hint="risk flags are explained on hover">
        <AccountsTable rows={d.accounts_detail} onOpen={openAccount} flash={flash} />
      </Collapsible>

      <Collapsible title="Narrative network" hint="who published in this narrative">
        <EgoGraph d={d} onOpen={openAccount} />
      </Collapsible>

      <Collapsible title="Publications" count={d.publications.length} hint="similarity = meaning similarity to the first publication">
        <ol className="divide-y divide-line">
          {d.publications.map((p, k) => (
            <li key={p.uid} id={`ev-P${k + 1}`} className={`grid grid-cols-[28px_150px_1fr_64px] gap-3 rounded py-2.5 ${flash === `P${k + 1}` ? "bg-[#fff3c4]" : ""}`}>
              <span className="num text-[12px] text-faint">P{k + 1}</span>
              <span className="text-[12.5px]"><PlatformBadge p={p.platform} /> <span className="text-[11.5px] uppercase text-muted">{p.format}</span> <span className="num block text-muted">{fmtTs(p.ts)}</span>
                <button onClick={() => openAccount(p.account_id)} className="num mt-0.5 block truncate text-left text-accent hover:underline">{p.account}</button></span>
              <span className="text-[13.5px] leading-snug">
                {p.url ? <a href={p.url} target="_blank" rel="noreferrer" className="hover:text-accent">{p.caption ?? p.text}</a> : (p.caption ?? p.text)}
                {p.transcript && <span className="mt-1 block text-[12.5px] italic text-muted"><b className="not-italic">Spoken:</b> “{p.transcript}”</span>}
                {p.ocr && <span className="mt-0.5 block text-[12.5px] italic text-muted"><b className="not-italic">On screen:</b> “{p.ocr}”</span>}
              </span>
              <span className="num text-right text-[12.5px] text-muted" title="Meaning similarity to publication #1">{p.similarity !== null ? `${Math.round(p.similarity * 100)}%` : "—"}</span>
            </li>
          ))}
        </ol>
      </Collapsible>

      <Collapsible title="Method" hint="how this was computed">
        <ul className="list-disc space-y-1 pl-5 text-[13px] text-muted">
          <li>A narrative groups publications (posts, reels, videos, articles) with near-identical text (MinHash), the same shared link, or the same meaning (embeddings), from at least 2 accounts.</li>
          <li>Severity is the sum of explained signals (bursts, new accounts, listed sources, cross-platform speed, stance). Review ≥ 0.40, Priority ≥ 0.70. A debunk is never an alert.</li>
          <li>Stance is assessed by a small LLM against the documented narrative and always quoted; it is one signal among others.</li>
          <li>Listed sources: EU-sanctioned Russian state media, Pravda network (VIGINUM / CheckFirst), outlets named by the US State Dept.</li>
        </ul>
      </Collapsible>
    </div>
  );
}

function Spread({ d }: { d: StoryDetail }) {
  const t0 = +new Date(d.first_ts), t1 = Math.max(t0 + 1, +new Date(d.last_ts));
  const plats = [...new Set(d.publications.map((p) => p.platform))];
  return (
    <div className="space-y-1.5">
      {plats.map((p) => (
        <div key={p} className="flex items-center gap-3">
          <span className="w-24 text-[12.5px] text-muted">{PLATFORM_NAME[p]}</span>
          <div className="relative h-5 flex-1 rounded bg-panel-2">
            {d.publications.filter((x) => x.platform === p).map((x) => (
              <span key={x.uid} title={`${x.account} · ${fmtTs(x.ts)}`}
                className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-panel"
                style={{ left: `${((+new Date(x.ts) - t0) / (t1 - t0)) * 100}%`, background: STANCE[d.stance].color }} />
            ))}
          </div>
        </div>
      ))}
      <div className="num flex justify-between pl-[108px] text-[11.5px] text-faint"><span>{fmtTs(d.first_ts)}</span><span>{fmtTs(d.last_ts)}</span></div>
    </div>
  );
}

export function AccountsTable({ rows, onOpen, flash }: { rows: Account[]; onOpen: (id: string) => void; flash?: string | null }) {
  return (
    <table className="w-full text-[13px]">
      <thead className="text-left text-[12px] text-muted">
        <tr className="border-b border-line"><th className="w-8 font-medium">#</th><th className="py-1.5 font-medium">Account</th><th className="font-medium">Platform</th><th className="font-medium">Risk flags</th><th className="text-right font-medium">Followers</th><th className="text-right font-medium">Posts</th></tr>
      </thead>
      <tbody>
        {rows.map((a, k) => (
          <tr key={a.id} id={`ev-A${k + 1}`} onClick={() => onOpen(a.id)} className={`cursor-pointer border-b border-line last:border-0 hover:bg-panel-2 ${flash === `A${k + 1}` ? "bg-[#fff3c4]" : ""}`}>
            <td className="num text-[11.5px] text-faint">A{k + 1}</td>
            <td className="num py-1.5 text-accent">{a.label}</td>
            <td><PlatformBadge p={a.platform} /></td>
            <td><FlagChips flags={a.flags} /></td>
            <td className="num text-right">{a.followers?.toLocaleString("en-US") ?? "—"}</td>
            <td className="num text-right">{a.items}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const riskColor = (r: string) => (r === "high" ? "var(--sev-priority)" : r === "medium" ? "var(--sev-review)" : "var(--sev-organic)");

/** Graphe en étoile lisible : l'histoire au centre, ses comptes autour, couleur = risque du compte. */
function EgoGraph({ d, onOpen }: { d: StoryDetail; onOpen: (id: string) => void }) {
  const accs = d.accounts_detail.slice(0, 24);
  const W = 640, H = 300, cx = W / 2, cy = H / 2, R = 120;
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
        {accs.map((a, i) => {
          const ang = (i / accs.length) * Math.PI * 2 - Math.PI / 2;
          const x = cx + Math.cos(ang) * R * 1.6, y = cy + Math.sin(ang) * R;
          return (
            <g key={a.id} onClick={() => onOpen(a.id)} className="cursor-pointer">
              <line x1={cx} y1={cy} x2={x} y2={y} stroke={STANCE[d.stance].color} strokeWidth={1.6} opacity={0.55} />
              <circle cx={x} cy={y} r={6 + Math.min(6, a.items)} fill={riskColor(a.risk)} stroke="#fff" strokeWidth={2} />
              <text x={x} y={y + 22} textAnchor="middle" fontSize={11} fill="var(--muted)" className="num">{a.label.slice(0, 22)}</text>
            </g>
          );
        })}
        <circle cx={cx} cy={cy} r={16} fill="var(--panel)" stroke={STANCE[d.stance].color} strokeWidth={3} />
        <text x={cx} y={cy + 4} textAnchor="middle" fontSize={11} fontWeight={600} fill="var(--text)">narrative</text>
      </svg>
      <div className="flex flex-wrap gap-4 text-[12px] text-muted">
        <span><b style={{ color: STANCE[d.stance].color }}>Line</b> = published in this narrative (colour = stance)</span>
        <span><b style={{ color: "var(--sev-priority)" }}>●</b> listed source / declared bot</span>
        <span><b style={{ color: "var(--sev-review)" }}>●</b> account &lt; 30 days</span>
        <span><b style={{ color: "var(--sev-organic)" }}>●</b> no risk flag</span>
      </div>
    </div>
  );
}


/** Arrivée sur chaque plateforme (première apparition dans NOS données, pas une origine) et sauts entre plateformes. */
function CrossPlatform({ d }: { d: StoryDetail }) {
  const dif = d.diffusion!;
  const t0 = +new Date(dif.entries[0].first_ts);
  return (
    <div className="mt-4 border-t border-line pt-3">
      <div className="text-[12.5px] font-semibold text-muted">ACROSS PLATFORMS</div>
      <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[13px]">
        {dif.entries.map((e, k) => (
          <span key={e.platform} className="flex items-center gap-1.5">
            {k > 0 && <span className="text-muted">→</span>}
            <PlatformBadge p={e.platform} />
            <span className="num text-[12px] text-muted">{k === 0 ? "first seen" : `+${fmtDelay((+new Date(e.first_ts) - t0) / 60000)}`}{e.precise ? "" : " (date only)"}</span>
          </span>
        ))}
      </div>
      <p className="mt-1 text-[11.5px] text-faint">First appearance in our data on each platform, not the origin: we do not see X or private groups.</p>
      {dif.hops.length > 0 && <div className="mt-2 -mx-4"><HopList hops={dif.hops} compact /></div>}
    </div>
  );
}
