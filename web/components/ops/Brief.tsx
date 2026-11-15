"use client";
import { useMemo, useState } from "react";
import { passes, useOps } from "@/lib/store";
import { useView } from "@/lib/useView";
import { PLATFORM_NAME, SEVERITY, STANCE, fmtDay, getSummary, type Stance } from "@/lib/views";
import { FirstRun } from "./Progress";
import { Pipeline } from "@/components/anim/Anim";
import { Collapsible, Empty, FlagChips, Kpi, PlatformBadge, Platforms, Section, SeverityBadge, Sparkline, StackedBars, StanceChip } from "@/components/ui/kit";

const ORDER: Stance[] = ["promotes", "neutral", "debunks", "unclassified"];
/** Mode « Alerts » : le rouge ne sert qu'à ce qui mérite un examen (narratifs signalés, comptes suspects, fausse affirmation). */
const ALERTS = [
  { key: "priority", label: "Priority narrative", color: "var(--sev-priority)" },
  { key: "review", label: "Needs review", color: "var(--sev-review)" },
  { key: "suspect", label: "Suspected account or false claim", color: "#f87171" },
  { key: "organic", label: "Narrative without alert", color: "#94a3b8" },
  { key: "none", label: "Not in a narrative", color: "#e2e8f0" },
];
type Mode = "alerts" | "stance" | "platform";

export default function Brief({ slug }: { slug: string }) {
  const showcase = useOps((x) => x.showcase);
  const { data } = useView(() => getSummary(slug), [slug]);
  const { filters, openStory, openAccount } = useOps();
  const [mode, setMode] = useState<Mode>("alerts");

  const range = useMemo(() => (data?.daily ?? []).map((d) => d.day), [data]);
  if (!data) return <div className="p-8"><Empty text="Loading the brief…" /></div>;
  if (data.kpis.stories === 0) return <div className="h-full overflow-y-auto p-6"><FirstRun /></div>;
  const k = data.kpis;
  const stories = data.stories.filter((s) => passes(filters, s));
  const platforms = Object.keys(data.platform_daily).filter((p) => passes(filters, { platform: p }));
  const platData = range.map((day) => ({ day, ...Object.fromEntries(platforms.map((p) => [p, Object.fromEntries(data.platform_daily[p])[day] ?? 0])) }));
  const shades = ["#334155", "#0a7aff", "#c4161c", "#0f172a", "#c13584", "#1c93e3", "#563acc"];
  const pcolor: Record<string, string> = { web: "#334155", bluesky: "#0a7aff", youtube: "#c4161c", tiktok: "#111827", instagram: "#c13584", telegram: "#1c93e3" };

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[1280px] space-y-6 p-6">
        {showcase && <Pipeline slug={slug} />}
        <Collapsible title="The campaign under watch" hint={`${data.event.start} → ${data.event.end} · ${data.event.languages.join(", ").toUpperCase()}`}>
          <p className="max-w-[880px] text-[14.5px] leading-relaxed">{data.event.description}</p>
          {data.event.sources.length > 0 && (
            <div className="mt-3">
              <div className="text-[12.5px] font-semibold text-muted">Reference fact-checks and investigations</div>
              <ul className="mt-1 space-y-0.5">
                {data.event.sources.map((u) => (
                  <li key={u}><a href={u} target="_blank" rel="noreferrer" className="text-[13px] text-accent hover:underline">{new URL(u).hostname.replace("www.", "")} — {u.split("/").filter(Boolean).pop()?.slice(0, 70)}</a></li>
                ))}
              </ul>
            </div>
          )}
          <div className="mt-3 text-[12.5px] text-muted">Search terms: <span className="text-text">{data.event.keywords.join(" · ")}</span></div>
        </Collapsible>

        <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
          <Kpi label="Publications" value={k.items} />
          <Kpi label="Accounts & sources" value={k.accounts} />
          <Kpi label="Platforms" value={k.platforms} />
          <Kpi label="Narratives" value={k.stories} help="Groups of posts, reels, videos and articles saying the same thing" />
          <Kpi label="Need review" value={k.priority + k.review} tone={k.priority ? "var(--sev-priority)" : "var(--sev-review)"} help="Priority + Review" />
          <Kpi label="Repeat the claim" value={k.promotes} tone="var(--st-promotes)" help="Narratives that repeat the documented false claim as true" />
          <Kpi label="Debunk it" value={k.debunks} tone="var(--st-debunks)" help="Fact-checks and refutations" />
        </div>

        <div className="rounded-md border border-line bg-panel p-4">
          <Section title="Activity over time"
            hint={mode === "platform" ? "publications per day, by platform" : mode === "stance" ? "publications per day, by stance of their narrative"
              : "publications per day · red = needs a look (flagged narrative, suspected account or false claim)"}
            right={
              <div className="inline-flex rounded-md border border-line text-[12.5px]">
                {([["Alerts", "alerts"], ["Stance", "stance"], ["Platform", "platform"]] as [string, Mode][]).map(([l, v]) => (
                  <button key={v} onClick={() => setMode(v)}
                    className={`px-3 py-1 ${mode === v ? "bg-accent text-white" : "text-muted hover:text-text"}`}>{l}</button>
                ))}
              </div>
            }>
            {mode === "platform"
              ? <StackedBars data={platData} keys={platforms.map((p, i) => ({ key: p, label: PLATFORM_NAME[p] ?? p, color: pcolor[p] ?? shades[i % shades.length] }))} />
              : mode === "stance"
                ? <StackedBars data={data.daily as never} keys={ORDER.map((s) => ({ key: s, label: STANCE[s].label, color: STANCE[s].color }))}
                    marks={data.peaks.map((p) => ({ day: p.period, label: p.explanation }))} />
                : <StackedBars data={(data.daily_alerts ?? []) as never} keys={ALERTS} marks={data.peaks.map((p) => ({ day: p.period, label: p.explanation }))} />}
            {data.peaks.length > 0 && (
              <div className="mt-3 rounded-md bg-panel-2 px-3 py-2 text-[13px]">
                <b>Burst detected:</b> {data.peaks.map((p) => `${fmtDay(p.period)} — ${p.explanation}`).join(" · ")}. A burst alone is not a sign of manipulation: real events create them too.
              </div>
            )}
          </Section>
        </div>

        <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
          <Section title="Narratives to review" hint="highest severity first">
            <div className="space-y-2">
              {stories.slice(0, 6).map((s) => (
                <button key={s.id} onClick={() => openStory(s.id)}
                  className="block w-full rounded-md border border-line bg-panel p-3 text-left shadow-sm hover:border-accent"
                  style={{ borderLeft: `5px solid ${SEVERITY[s.level]?.color ?? "var(--line)"}` }}>
                  <div className="flex items-center gap-3">
                    <SeverityBadge level={s.level} size="sm" /><StanceChip stance={s.stance} />
                    <span className="ml-auto"><Platforms list={s.platforms} /></span>
                  </div>
                  <div className="mt-2 line-clamp-2 text-[14px] font-medium leading-snug">{s.title}</div>
                  <div className="mt-2 flex items-center gap-3 text-[12.5px] text-muted">
                    <span className="num">{s.accounts} accounts · {s.items} posts</span>
                    <span className="truncate">{s.headline_signal ?? "No coordination signal"}</span>
                    <span className="ml-auto"><Sparkline days={s.days} range={range} /></span>
                  </div>
                </button>
              ))}
              {stories.length === 0 && <Empty text="No narrative matches the filters." />}
            </div>
          </Section>

          <div className="space-y-6">
            <Section title="Platforms" hint="same time axis">
              <div className="divide-y divide-line rounded-md border border-line bg-panel">
                {platforms.map((p) => {
                  const total = data.platform_daily[p].reduce((a, [, n]) => a + n, 0);
                  return (
                    <div key={p} className="flex items-center gap-3 px-3 py-2">
                      <span className="w-12"><PlatformBadge p={p} /></span>
                      <span className="w-20 text-[13px]">{PLATFORM_NAME[p]}</span>
                      <Sparkline days={data.platform_daily[p]} range={range} width={170} />
                      <span className="num ml-auto text-[13px]">{total}</span>
                    </div>
                  );
                })}
              </div>
            </Section>
            <Section title="Top amplifiers" hint="accounts in most narratives">
              <div className="divide-y divide-line rounded-md border border-line bg-panel">
                {data.top_accounts.filter((a) => passes(filters, { platform: a.platform })).map((a) => (
                  <button key={a.id} onClick={() => openAccount(a.id)} className="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-panel-2">
                    <PlatformBadge p={a.platform} />
                    <span className="num min-w-0 flex-1 truncate text-[13px]">{a.label}</span>
                    <FlagChips flags={a.flags} />
                    <span className="num w-16 text-right text-[12.5px] text-muted">{a.stories.length} narr.</span>
                  </button>
                ))}
              </div>
            </Section>
          </div>
        </div>
        <p className="text-[12px] text-faint">Range: {range.length ? `${fmtDay(range[0])} – ${fmtDay(range[range.length - 1])}` : "—"}. Off-topic items are filtered out before any count.</p>
      </div>
    </div>
  );
}
