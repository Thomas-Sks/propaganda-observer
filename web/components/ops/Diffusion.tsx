"use client";
import { useOps } from "@/lib/store";
import { useView } from "@/lib/useView";
import { PLATFORM_NAME, getDiffusion, type Flow, type Hop } from "@/lib/views";
import { Empty, PlatformBadge } from "@/components/ui/kit";

/* Échelle de temps logarithmique commune : 1 min → 3 jours. */
const T_MIN = 1, T_MAX = 72 * 60;
const pos = (m: number) => (Math.log(Math.min(T_MAX, Math.max(T_MIN, m))) - Math.log(T_MIN)) / (Math.log(T_MAX) - Math.log(T_MIN)) * 100;
const TICKS: [number, string][] = [[1, "1 min"], [5, "5 min"], [15, "15 min"], [60, "1 h"], [360, "6 h"], [1440, "1 day"], [4320, "3 days"]];
export const fmtDelay = (m: number) => (m < 60 ? `${Math.round(m)} min` : m < 1440 ? `${(m / 60).toFixed(1)} h` : `${(m / 1440).toFixed(1)} days`);
const PROVEN = "#c026d3", INFERRED = "#94a3b8";

export default function Diffusion({ slug }: { slug: string }) {
  const { data } = useView(() => getDiffusion(slug), [slug]);
  if (!data) return <div className="p-8"><Empty text="Measuring how content moves between platforms…" /></div>;
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[1300px] space-y-5 p-5">
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <h2 className="text-[18px] font-semibold">How content moves between platforms</h2>
          <span className="text-[13px] text-muted">{data.n_hops} cross-platform hops observed · minutes suggest an organised relay, hours suggest people sharing</span>
          <details className="relative ml-auto text-[13px]">
            <summary className="cursor-pointer text-accent">How is this measured?</summary>
            <ul className="absolute right-0 z-20 mt-2 w-[540px] list-disc space-y-1 rounded-md border border-line bg-panel p-3 pl-7 text-[12.5px] shadow-lg">
              {data.method.map((m) => <li key={m}>{m}</li>)}
            </ul>
          </details>
        </div>

        <section className="rounded-md border border-line bg-panel">
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-line px-4 py-2.5 text-[12.5px] text-muted">
            <b className="text-text">Each dot is one hop, placed by its delay</b>
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full" style={{ background: PROVEN }} />proven (cites or links the source)</span>
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full border border-[#64748b]" style={{ background: INFERRED }} />inferred (closest earlier text)</span>
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-4 rounded-sm bg-sev-priority/15" />relay speed (≤ {data.fast_min} min)</span>
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-4 rounded-sm bg-[#e2e8f0]" />organic sharing (&gt; {data.slow_min / 60} h)</span>
          </div>
          {data.flows.length === 0 ? <div className="p-4"><Empty text="No cross-platform hop observed with precise timestamps." /></div> : (
            <div className="px-4 py-3">
              <div className="grid grid-cols-[230px_1fr_200px] items-end gap-x-4 pb-1 text-[11.5px] text-muted">
                <span>From → to</span>
                <div className="relative h-4">{TICKS.map(([m, l], k) => (
                  <span key={m} className={`num absolute whitespace-nowrap ${k === TICKS.length - 1 ? "-translate-x-full" : k === 0 ? "" : "-translate-x-1/2"}`} style={{ left: `${pos(m)}%` }}>{l}</span>
                ))}</div>
                <span className="text-right">median delay · within {data.fast_min} min</span>
              </div>
              {data.flows.map((f) => <FlowRow key={f.from + f.to} f={f} fast={data.fast_min} slow={data.slow_min} />)}
            </div>
          )}
        </section>

        <section className="rounded-md border border-line bg-panel">
          <div className="border-b border-line px-4 py-2.5">
            <b className="text-[14px]">Fastest hops</b>
            <span className="ml-2 text-[12.5px] text-muted">who took up whom, and how fast · click to open the narrative</span>
          </div>
          <HopList hops={data.hops.slice(0, 40)} />
        </section>
      </div>
    </div>
  );
}

function FlowRow({ f, fast, slow }: { f: Flow; fast: number; slow: number }) {
  return (
    <div className="grid grid-cols-[230px_1fr_200px] items-center gap-x-4 border-t border-line py-2.5">
      <div className="flex items-center gap-1.5 text-[13px]">
        <PlatformBadge p={f.from} /><span className="text-muted">→</span><PlatformBadge p={f.to} />
        <span className="num ml-1 text-[12px] text-muted">{f.n} hop{f.n > 1 ? "s" : ""}{f.proven ? ` · ${f.proven} proven` : ""}</span>
      </div>
      <div className="relative h-7 rounded-sm bg-panel-2">
        <span className="absolute inset-y-0 left-0 bg-sev-priority/15" style={{ width: `${pos(fast)}%` }} />
        <span className="absolute inset-y-0 right-0 bg-[#e2e8f0]" style={{ left: `${pos(slow)}%` }} />
        <span className="absolute top-1/2 h-[2px] -translate-y-1/2 bg-[#334155]/40" style={{ left: `${pos(f.p25_min)}%`, width: `${Math.max(0.5, pos(f.p75_min) - pos(f.p25_min))}%` }} />
        {f.delays.map((d, k) => (
          <span key={k} title={`${fmtDelay(d.min)} · ${d.kind}`}
            className={`absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full ${d.kind === "proven" ? "" : "border border-[#64748b]"}`}
            style={{ left: `${pos(d.min)}%`, background: d.kind === "proven" ? PROVEN : INFERRED, marginTop: `${((k % 3) - 1) * 4}px` }} />
        ))}
        <span className="absolute top-0 h-full w-[2px] -translate-x-1/2 bg-text" style={{ left: `${pos(f.median_min)}%` }} title={`median ${fmtDelay(f.median_min)}`} />
      </div>
      <div className="text-right text-[12.5px]">
        <span className="num font-semibold">{fmtDelay(f.median_min)}</span>
        <span className="num ml-2 text-muted">{Math.round(f.fast_share * 100)}% fast</span>
      </div>
    </div>
  );
}

export function HopList({ hops, compact = false }: { hops: Hop[]; compact?: boolean }) {
  const { openStory, openAccount } = useOps();
  if (!hops.length) return <div className="p-4 text-[13px] text-muted">No cross-platform hop observed.</div>;
  return (
    <ul className="divide-y divide-line">
      {hops.map((h) => (
        <li key={h.from_uid + h.to_uid} className={`grid gap-x-3 px-4 py-2.5 text-[13px] ${compact ? "grid-cols-[1fr_auto]" : "grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_auto]"}`}>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-1.5">
              <PlatformBadge p={h.from_platform} />
              <button onClick={() => openAccount(h.from_author)} className="num text-accent hover:underline">{h.from_label}</button>
              <span className="text-muted">→</span>
              <PlatformBadge p={h.to_platform} />
              <button onClick={() => openAccount(h.to_author)} className="num text-accent hover:underline">{h.to_label}</button>
            </div>
            <div className="mt-0.5 text-[12px] text-muted">
              <span className={h.kind === "proven" ? "font-semibold" : ""} style={{ color: h.kind === "proven" ? PROVEN : undefined }}>{h.kind}</span>: {h.why}
            </div>
          </div>
          {!compact && (
            <button onClick={() => { if (h.story) openStory(h.story); }} disabled={!h.story}
              className="min-w-0 text-left text-[12.5px] italic text-muted hover:text-text disabled:cursor-default">
              <span className="line-clamp-2">“{h.text}”</span>
            </button>
          )}
          <div className="text-right">
            <div className="num text-[15px] font-semibold">{fmtDelay(h.delay_min)}</div>
            <div className="num text-[11px] text-muted">{PLATFORM_NAME[h.from_platform] ?? h.from_platform} → {PLATFORM_NAME[h.to_platform] ?? h.to_platform}</div>
          </div>
        </li>
      ))}
    </ul>
  );
}
