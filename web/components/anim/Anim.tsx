"use client";
/* Animations explicatives, dans le style de l'intro (fond nuit, cyan lumineux, Orbitron).
   Elles montrent CE QUI SE PASSE, sans chiffres : le détail chiffré est dans l'onglet, juste en dessous.
   Exemples tirés des vues publiées ; les transcriptions sont des extraits réels figés (samples.ts). */
import { useEffect, useId, useMemo, useState } from "react";
import { useOps, type Tab } from "@/lib/store";
import { useView } from "@/lib/useView";
import { PLATFORM_NAME, getSummary, type Coordination, type Diffusion, type StoryCard } from "@/lib/views";
import { TRANSCRIPTS } from "./samples";
import "./anim.css";

const WATCHED = ["youtube", "bluesky", "tiktok", "instagram", "telegram", "web"];
const later = (m: number) => (m < 60 ? "minutes later" : m < 1440 ? "hours later" : "days later");
const SEV = (lvl: string) => (lvl === "priority" ? "#ff4d6a" : lvl === "review" ? "#ffaa2b" : "#22c5ee");

function useTick(ms: number) {
  const [n, setN] = useState(0);
  useEffect(() => { const id = setInterval(() => setN((x) => x + 1), ms); return () => clearInterval(id); }, [ms]);
  return n;
}
/** Halo lumineux SVG (même rendu que l'intro). */
function Glow({ id, s = 2.4 }: { id: string; s?: number }) {
  return (
    <defs>
      <filter id={id} x="-50%" y="-50%" width="200%" height="200%">
        <feGaussianBlur stdDeviation={s} result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
      </filter>
    </defs>
  );
}
function Chip({ p }: { p: string }) { return <span className="av-chip">{(PLATFORM_NAME[p] ?? p).toUpperCase()}</span>; }

/* ---------- Bandeau repliable (préférence mémorisée dans le navigateur) ---------- */
export function Strip({ id, title, caption, children }: { id: string; title: string; caption: string; children: React.ReactNode }) {
  const key = `anim-hidden:${id}`;
  const [hidden, setHidden] = useState(false);
  useEffect(() => { const t = setTimeout(() => { try { setHidden(localStorage.getItem(key) === "1"); } catch {} }, 0); return () => clearTimeout(t); }, [key]);
  const toggle = () => { setHidden(!hidden); try { localStorage.setItem(key, hidden ? "0" : "1"); } catch {} };
  if (hidden) return <button onClick={toggle} className="av-show">▶ Show how it works</button>;
  return (
    <section className="av-strip">
      <div className="av-grid" />
      <header><span className="av-live" /><b>{title}</b><span>{caption}</span><button onClick={toggle}>Hide</button></header>
      <div className="relative">{children}</div>
    </section>
  );
}

/* ---------- 1. Collecte ---------- */
export function Collect() {
  return (
    <div className="av-collect">
      {WATCHED.map((p, k) => (
        <div key={p} className="av-lane">
          <span className="av-radar" style={{ animationDelay: `${k * 0.4}s` }}><Chip p={p} /></span>
          <span className="av-track">{[0, 1, 2].map((j) => <i key={j} style={{ animationDelay: `${k * 0.37 + j * 0.9}s`, animationDuration: `${2.2 + (k % 3) * 0.5}s` }} />)}</span>
        </div>
      ))}
    </div>
  );
}

/* ---------- 2. Écoute Whisper ---------- */
export function Listen() {
  const cycle = useTick(9000) % TRANSCRIPTS.length;
  return <ListenOne key={cycle} s={TRANSCRIPTS[cycle]} />;
}
function ListenOne({ s }: { s: (typeof TRANSCRIPTS)[number] }) {
  const n = useTick(120);
  const words = useMemo(() => s.text.split(" "), [s]);
  const shown = words.slice(0, Math.min(words.length, n + 1)).slice(-22).join(" ");
  return (
    <div className="av-listen">
      <div className="av-video">
        <span className="av-scan" />
        <span className="av-play">▶</span>
        <span className="av-vtag"><Chip p={s.platform} /></span>
        <span className="av-progress" />
      </div>
      <div className="av-wave">{Array.from({ length: 32 }, (_, i) => <i key={i} style={{ animationDelay: `${(i * 0.07) % 0.9}s` }} />)}</div>
      <div className="av-transcript"><b>WHISPER</b>“{shown}<span className="av-caret">▍</span>”</div>
    </div>
  );
}

/* ---------- 3. Regroupement en narratifs ---------- */
export function Group({ stories }: { stories: StoryCard[] }) {
  const gid = useId().replace(/:/g, "");
  const phase = useTick(2600) % 2;  // 0 = publications éparses, 1 = regroupées par narratif
  const top = stories.slice(0, 3);
  const centres = [[60, 52], [160, 52], [260, 52]];
  return (
    <div className="av-group">
      <svg viewBox="0 0 320 104" className="w-full">
        <Glow id={gid} />
        {top.map((s, c) => (
          <circle key={s.id} cx={centres[c][0]} cy={centres[c][1]} r={32} fill="none" stroke={SEV(s.level)} strokeWidth={1}
            strokeDasharray="3 4" opacity={phase ? 0.8 : 0} className="av-tr" />
        ))}
        <g filter={`url(#${gid})`}>
          {Array.from({ length: 30 }, (_, i) => {
            const c = i % 3, r1 = Math.sin(i * 12.9898) * 43758.5453, r2 = Math.sin(i * 78.233) * 12345.6789;
            const fx = (r1 - Math.floor(r1)) * 300 + 10, fy = (r2 - Math.floor(r2)) * 84 + 10;
            const a = (i / 30) * Math.PI * 6, rr = 6 + (i % 4) * 5;
            const x = phase ? centres[c][0] + Math.cos(a) * rr : fx, y = phase ? centres[c][1] + Math.sin(a) * rr : fy;
            return <circle key={i} r={3.2} fill={phase && top[c] ? SEV(top[c].level) : "#7fe6ff"} style={{ transform: `translate(${x}px, ${y}px)` }} className="av-tr" />;
          })}
        </g>
      </svg>
      <div className="grid grid-cols-3 gap-2">
        {top.map((s) => <span key={s.id} className={`av-label line-clamp-2 ${phase ? "opacity-100" : "opacity-0"}`}>{s.title}</span>)}
      </div>
    </div>
  );
}

/* ---------- 4. Liens entre comptes et narratifs ---------- */
export function Link() {
  const gid = useId().replace(/:/g, "");
  const hubs: [number, number][] = [[70, 42], [250, 42], [160, 104]];
  const accs: [number, number, number[]][] = [[30, 98], [115, 72], [205, 72], [290, 98], [160, 16], [118, 130]].map(([x, y], i) =>
    [x, y, [[0], [0, 2], [1, 2], [1], [0, 1], [2]][i]] as [number, number, number[]]);
  return (
    <div className="av-link">
      <svg viewBox="0 0 320 142" className="w-full">
        <Glow id={gid} />
        {accs.flatMap(([x, y, hs], i) => hs.map((h) => <line key={`${i}-${h}`} x1={x} y1={y} x2={hubs[h][0]} y2={hubs[h][1]} className="av-draw" style={{ animationDelay: `${i * 0.25}s` }} />))}
        <line x1={115} y1={72} x2={205} y2={72} className="av-syncline" filter={`url(#${gid})`} />
        <text x={160} y={64} textAnchor="middle" className="av-synctxt">same text, same moment</text>
        <g filter={`url(#${gid})`}>
          {hubs.map(([x, y], i) => <circle key={i} cx={x} cy={y} r={10} fill={i === 2 ? "#ff4d6a" : "#22c5ee"} opacity={0.9} />)}
          {accs.map(([x, y, hs], i) => <circle key={i} cx={x} cy={y} r={4.5} fill={hs.length > 1 ? "#ffaa2b" : "#bff8ff"} />)}
        </g>
      </svg>
      <div className="av-legend"><span><i style={{ background: "#22c5ee" }} />narrative</span><span><i style={{ background: "#bff8ff" }} />account</span><span><i style={{ background: "#ffaa2b" }} />bridge</span></div>
    </div>
  );
}

/* ---------- Coordination : deux comptes, la même action, au même moment ---------- */
export function Sync({ coord }: { coord: Coordination }) {
  const ex = useMemo(() => {
    const lab = new Map(coord.nodes.map((n) => [n.id, n.label]));
    const e = [...coord.edges].filter((x) => x.examples.length).sort((a, b) => a.examples[0].delay_s - b.examples[0].delay_s)[0];
    return e ? { a: lab.get(e.source) ?? "", b: lab.get(e.target) ?? "", x: e.examples[0] } : null;
  }, [coord]);
  const loop = useTick(6500);
  if (!ex) return null;
  const what = ex.x.kind === "link" ? ex.x.key : ex.x.text || ex.x.key;
  return (
    <div key={loop} className="av-sync">
      <div className="av-post" style={{ animationDelay: "0.2s" }}><b>{ex.a}</b><p>{what.slice(0, 120)}</p></div>
      <div className="av-bracket"><span>same {ex.x.kind}</span><b>same moment</b></div>
      <div className="av-post" style={{ animationDelay: "0.9s" }}><b>{ex.b}</b><p>{what.slice(0, 120)}</p></div>
    </div>
  );
}

/* ---------- Diffusion : un contenu saute d'une plateforme à l'autre ---------- */
export function Relay({ diffusion }: { diffusion: Diffusion }) {
  const gid = useId().replace(/:/g, "");
  const h = diffusion.hops.find((x) => x.kind === "proven") ?? diffusion.hops[0];
  const tick = useTick(40);
  if (!h) return null;
  const u = Math.min(1, ((tick * 40) % 5000) / 3400);
  const e = u < 0.5 ? 2 * u * u : 1 - (-2 * u + 2) ** 2 / 2;
  const x = (1 - e) ** 2 * 10 + 2 * (1 - e) * e * 200 + e * e * 390, y = (1 - e) ** 2 * 80 + 2 * (1 - e) * e * -20 + e * e * 80;
  return (
    <div className="av-relay">
      <div className="av-end"><Chip p={h.from_platform} /><b>{h.from_label}</b></div>
      <svg viewBox="0 0 400 96" className="av-arc">
        <Glow id={gid} s={3} />
        <path d="M10 80 Q200 -20 390 80" />
        <circle cx={x} cy={y} r={7} fill="#ff3df2" filter={`url(#${gid})`} />
        <text x="200" y="48" textAnchor="middle" className="av-later" opacity={e}>{later(h.delay_min)}</text>
      </svg>
      <div className="av-end"><Chip p={h.to_platform} /><b>{h.to_label}</b></div>
      <div className="av-why"><b>{h.kind === "proven" ? "Proven" : "Inferred"}</b>: {h.why}</div>
    </div>
  );
}

/* ---------- Brief : la chaîne complète, étape par étape ---------- */
const STEPS: { title: string; caption: string; tab: Tab }[] = [
  { title: "Collect", caption: "public posts, live, on every platform", tab: "accounts" },
  { title: "Listen", caption: "every video is transcribed by Whisper", tab: "stories" },
  { title: "Group", caption: "posts saying the same thing become a narrative", tab: "stories" },
  { title: "Connect", caption: "who acts together, and how content jumps", tab: "coordination" },
];
export function Pipeline({ slug }: { slug: string }) {
  const { data: s } = useView(() => getSummary(slug), [slug]);
  const active = useTick(3500) % STEPS.length;
  const setTab = useOps((x) => x.setTab);
  if (!s) return null;
  return (
    <Strip id="pipeline" title="How Para-Celsus works" caption="on this observation">
      <div className="av-pipeline">
        {STEPS.map((st, k) => (
          <button key={st.title} onClick={() => setTab(st.tab)} className={`av-step ${k === active ? "on" : ""}`}>
            <div className="av-step-h"><span>{k + 1}</span><b>{st.title}</b></div>
            <div className="av-step-c">{st.caption}</div>
            <div className="av-step-body">
              {k === 0 && <Collect />}
              {k === 1 && <Listen />}
              {k === 2 && <Group stories={s.stories.filter((x) => x.level !== "insufficient_data")} />}
              {k === 3 && <Link />}
            </div>
            {k < STEPS.length - 1 && <span className="av-arrow">›</span>}
          </button>
        ))}
      </div>
    </Strip>
  );
}

/* ---------- Bandeaux par onglet ---------- */
export function StoriesAnim({ slug }: { slug: string }) {
  const { data: s } = useView(() => getSummary(slug), [slug]);
  if (!s) return null;
  return (
    <Strip id="stories" title="Listen, then group" caption="videos are transcribed, then everything saying the same thing becomes one narrative">
      <div className="av-wide"><Listen /><Group stories={s.stories} /></div>
    </Strip>
  );
}
export function CoordinationAnim({ coord }: { coord: Coordination }) {
  return (
    <Strip id="coordination" title="Same action, same moment" caption="accounts that post the same thing at the same time, again and again">
      <div className="px-5 pb-4"><Sync coord={coord} /></div>
    </Strip>
  );
}
export function DiffusionAnim({ diffusion }: { diffusion: Diffusion }) {
  return (
    <Strip id="diffusion" title="A jump between platforms" caption="minutes later looks like an organised relay, days later like people sharing">
      <div className="px-5 pb-4"><Relay diffusion={diffusion} /></div>
    </Strip>
  );
}
