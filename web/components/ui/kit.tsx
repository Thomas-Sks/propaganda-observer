"use client";
import { useState } from "react";
import { PLATFORM, PLATFORM_NAME, SEVERITY, STANCE, fmtDay, type Flag, type Signal, type Stance } from "@/lib/views";

/* ---------- Badges : chaque couleur porte UNE information, toujours doublée d'un libellé ---------- */

export function SeverityBadge({ level, size = "md" }: { level: string; size?: "sm" | "md" }) {
  const m = SEVERITY[level] ?? SEVERITY.organic;
  return (
    <span title={m.help}
      className={`inline-flex items-center gap-1 rounded-full font-bold uppercase tracking-[0.04em] text-white ${size === "sm" ? "px-2 text-[11px] leading-5" : "px-2.5 text-[12px] leading-6"}`}
      style={{ background: m.color }}>
      {level === "priority" ? "●" : level === "review" ? "◐" : "○"} {m.label}
    </span>
  );
}

export function StanceChip({ stance, full = false }: { stance: Stance; full?: boolean }) {
  const m = STANCE[stance];
  if (!m || stance === "unclassified") return null;
  return (
    <span title={m.help} className="inline-flex items-center gap-1 rounded-full px-2 text-[12.5px] font-semibold leading-6"
      style={{ color: m.color, background: `color-mix(in srgb, ${m.color} 13%, white)` }}>
      <span aria-hidden className="text-[10px]">{m.icon}</span>{full ? m.label : m.short}
    </span>
  );
}

const PCOLOR: Record<string, string> = {
  web: "#334155", bluesky: "#0a7aff", youtube: "#c4161c", tiktok: "#0f172a", instagram: "#c13584",
  telegram: "#1c93e3", x: "#0f172a", mastodon: "#563acc", facebook: "#1877f2",
};

export function PlatformBadge({ p }: { p: string }) {
  const c = PCOLOR[p] ?? "#334155";
  return (
    <span title={PLATFORM_NAME[p] ?? p}
      className="num inline-flex h-5 items-center rounded-[4px] px-1.5 text-[10.5px] font-bold tracking-wide"
      style={{ color: c, background: `color-mix(in srgb, ${c} 10%, white)`, boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${c} 35%, white)` }}>
      {PLATFORM[p] ?? p.toUpperCase()}
    </span>
  );
}

export function Platforms({ list }: { list: string[] }) {
  return <span className="inline-flex flex-wrap gap-1">{list.map((p) => <PlatformBadge key={p} p={p} />)}</span>;
}

export function FlagChips({ flags }: { flags: Flag[] }) {
  if (!flags.length) return <span className="text-[12px] text-faint">—</span>;
  const col = (r: Flag["risk"]) => (r === "high" ? "var(--sev-priority)" : r === "medium" ? "var(--sev-review)" : "var(--sev-organic)");
  return (
    <span className="inline-flex flex-wrap gap-1">
      {flags.map((f) => (
        <span key={f.key} title={f.detail} className="rounded-[3px] px-1.5 text-[11.5px] leading-5"
          style={{ color: col(f.risk), boxShadow: `inset 0 0 0 1px ${col(f.risk)}` }}>{f.label}</span>
      ))}
    </span>
  );
}

/* ---------- Structure ---------- */

export function Collapsible({ title, hint, defaultOpen = false, children, count }: {
  title: string; hint?: string; defaultOpen?: boolean; children: React.ReactNode; count?: number;
}) {
  return (
    <details open={defaultOpen} className="group rounded-md border border-line bg-panel">
      <summary className="flex items-center gap-2 rounded-t-md bg-panel-2 px-4 py-3 hover:bg-[#e9edf4]">
        <span className="chev text-[11px] text-accent transition-transform">▶</span>
        <span className="text-[15px] font-bold">{title}</span>
        {count !== undefined && <span className="num rounded-full bg-panel-2 px-2 text-[12px] text-muted">{count}</span>}
        {hint && <span className="ml-auto text-[12.5px] text-faint">{hint}</span>}
      </summary>
      <div className="border-t border-line px-4 py-3">{children}</div>
    </details>
  );
}

export function Section({ title, hint, children, right }: { title: string; hint?: string; children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <section>
      <div className="mb-2 flex items-baseline gap-3">
        <h2 className="text-[17px] font-bold">{title}</h2>
        {hint && <span className="text-[12.5px] text-faint">{hint}</span>}
        {right && <span className="ml-auto">{right}</span>}
      </div>
      {children}
    </section>
  );
}

export function Kpi({ label, value, tone, help }: { label: string; value: number | string; tone?: string; help?: string }) {
  return (
    <div className="rounded-md border border-line bg-panel px-4 py-3 shadow-sm" title={help}
      style={{ borderTop: `4px solid ${tone ?? "var(--navy)"}`, background: tone ? `color-mix(in srgb, ${tone} 6%, white)` : undefined }}>
      <div className="text-[13px] font-medium text-muted">{label}</div>
      <div className="num mt-1 text-[28px] font-bold leading-none" style={{ color: tone ?? "var(--text)" }}>{value}</div>
    </div>
  );
}

export function Empty({ text }: { text: string }) {
  return <div className="rounded-md border border-dashed border-line-strong p-8 text-center text-[13px] text-faint">{text}</div>;
}

/* ---------- Données ---------- */

export function SignalBars({ signals }: { signals: Signal[] }) {
  const list = signals.filter((s) => !s.name.startsWith("stance_"));
  return (
    <ul className="divide-y divide-line">
      {list.map((s) => (
        <li key={s.name} className="grid grid-cols-[1fr_120px] items-center gap-4 py-2">
          <span className={`text-[13.5px] ${s.weight > 0 ? "text-text" : "text-muted"}`}>{s.explanation}</span>
          <span className="flex items-center gap-2">
            <span className="h-1.5 flex-1 rounded-full bg-line">
              <span className="block h-1.5 rounded-full" style={{ width: `${Math.min(100, (s.weight / 0.5) * 100)}%`, background: s.weight >= 0.4 ? "var(--sev-priority)" : s.weight >= 0.2 ? "var(--sev-review)" : "var(--accent)" }} />
            </span>
            <span className="num w-9 text-right text-[12px] text-muted">{s.weight > 0 ? `+${s.weight.toFixed(2)}` : "0"}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

export function Sparkline({ days, range, width = 96, height = 22 }: { days: [string, number][]; range: string[]; width?: number; height?: number }) {
  if (!range.length) return null;
  const m = new Map(days);
  const vals = range.map((d) => m.get(d) ?? 0);
  const max = Math.max(1, ...vals);
  const bw = width / vals.length;
  return (
    <svg width={width} height={height} className="block" aria-hidden>
      {vals.map((v, k) => (
        <rect key={k} x={k * bw + 0.5} y={height - (v / max) * height} width={Math.max(1, bw - 1)} height={(v / max) * height}
          fill={v ? "var(--muted)" : "var(--line)"} />
      ))}
    </svg>
  );
}

/** Barres empilées par jour. `keys` dans l'ordre d'empilement (bas → haut), avec leur couleur. */
export function StackedBars({ data, keys, height = 180, marks = [] }: {
  data: ({ day: string } & Record<string, number | string>)[];
  keys: { key: string; label: string; color: string }[];
  height?: number;
  marks?: { day: string; label: string }[];  // pics détectés : repère au-dessus de la barre
}) {
  const [hover, setHover] = useState<number | null>(null);
  const totals = data.map((d) => keys.reduce((a, k) => a + (Number(d[k.key]) || 0), 0));
  const max = Math.max(1, ...totals);
  const W = 100 / Math.max(1, data.length);
  return (
    <div>
      <div className="flex flex-wrap gap-4 pb-2 text-[12.5px] text-muted">
        {keys.map((k) => (
          <span key={k.key} className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: k.color }} />{k.label}</span>
        ))}
      </div>
      <div className="relative" style={{ height: height + 24 }}>
        <div className="absolute inset-x-0 bottom-0 top-6 flex items-end gap-[3px]">
          {data.map((d, i) => (
            <div key={d.day} className="relative flex h-full flex-1 flex-col-reverse" style={{ width: `${W}%` }}
              onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              {keys.map((k) => {
                const v = Number(d[k.key]) || 0;
                return v ? <div key={k.key} style={{ height: `${(v / max) * 100}%`, background: k.color }} /> : null;
              })}
              {marks.some((m) => m.day === d.day) && (
                <div className="absolute left-1/2 -translate-x-1/2 whitespace-nowrap rounded-[3px] border border-text bg-panel px-1 text-[10.5px] font-semibold"
                  style={{ bottom: `calc(${(totals[i] / max) * 100}% + 4px)` }} title={marks.find((m) => m.day === d.day)?.label}>PEAK</div>
              )}
              {hover === i && (
                <div className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-1 w-44 -translate-x-1/2 rounded-md border border-line-strong bg-panel p-2 text-[12px] shadow-[0_6px_20px_rgba(20,30,50,.12)]">
                  <div className="font-semibold">{fmtDay(d.day)} · <span className="num">{totals[i]}</span></div>
                  {keys.map((k) => Number(d[k.key]) ? (
                    <div key={k.key} className="flex justify-between"><span style={{ color: k.color }}>{k.label}</span><span className="num">{d[k.key]}</span></div>
                  ) : null)}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
      <div className="mt-1 flex gap-[3px] text-[11px] text-faint">
        {data.map((d, i) => <div key={d.day} className="num flex-1 text-center">{i % Math.ceil(data.length / 8) === 0 ? fmtDay(d.day) : ""}</div>)}
      </div>
    </div>
  );
}
