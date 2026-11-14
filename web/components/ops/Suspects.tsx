"use client";
import { useState } from "react";
import { useOps, passes } from "@/lib/store";
import { useView } from "@/lib/useView";
import { getSuspects } from "@/lib/views";
import { PlatformBadge } from "@/components/ui/kit";

const LEVEL = {
  likely: { label: "Likely coordinated or automated", cls: "bg-sev-priority text-white" },
  review: { label: "To review", cls: "bg-sev-review text-white" },
} as const;

/** Liste des comptes au comportement coordonné, chacun avec ses preuves. Repliable. */
export default function Suspects({ slug }: { slug: string }) {
  const { data } = useView(() => getSuspects(slug), [slug]);
  const { filters, openAccount } = useOps();
  const [open, setOpen] = useState(true);
  const [all, setAll] = useState(false);
  if (!data) return null;
  const rows = data.accounts.filter((a) => passes(filters, { platform: a.platform }));
  const likely = rows.filter((r) => r.level === "likely").length;
  const shown = all ? rows : rows.slice(0, 15);
  return (
    <section className="mb-6 overflow-hidden rounded-md border-2 border-sev-priority/40 bg-panel">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-3 bg-sev-priority/10 px-4 py-3 text-left">
        <span className="text-[15px] font-semibold">Suspected coordinated accounts</span>
        <span className="num rounded-full bg-sev-priority px-2 text-[12px] font-semibold text-white">{likely} likely</span>
        <span className="num rounded-full bg-sev-review px-2 text-[12px] font-semibold text-white">{rows.length - likely} to review</span>
        <span className="ml-auto text-[12.5px] text-muted">{open ? "▾ hide" : "▸ show"}</span>
      </button>
      {open && (
        <>
          <p className="border-b border-line px-4 py-2 text-[12.5px] text-muted">
            Ranked on behaviour, not opinion: same text or link as other accounts within {data.window_min} min, the same
            partners again across narratives, repeated reposts, machine-like cadence, plus listed sources and new accounts.
            Posting volume alone is weak evidence (on Cresci-2017, ≥ 72 posts/day flags 3.7 % of genuine users), so it never makes an account “likely” on its own.
            “Coordinated” is not “fake”: a union and its local branches relaying one call are coordinated and authentic — read the evidence.
          </p>
          {rows.length === 0 ? <div className="p-4 text-[13px] text-muted">No account shows coordinated behaviour in this observation.</div> : (
            <ol className="divide-y divide-line">
              {shown.map((a, k) => (
                <li key={a.id} className="grid grid-cols-[28px_1fr_auto] gap-3 px-4 py-3 hover:bg-panel-2">
                  <span className="num pt-0.5 text-[13px] text-muted">{k + 1}</span>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <button onClick={() => openAccount(a.id)} className="num text-[14px] font-semibold text-accent hover:underline">{a.label}</button>
                      <PlatformBadge p={a.platform} />
                      <span className={`rounded px-1.5 text-[11.5px] font-semibold ${LEVEL[a.level].cls}`}>{LEVEL[a.level].label}</span>
                      {a.declared_bot && <span className="rounded border border-line-strong px-1.5 text-[11.5px] text-muted" title="The account carries Bluesky's 'automated' label: a transparent bot, not a covert one">declared bot</span>}
                      {a.posts_per_day != null && a.posts_per_day >= 72 && <span className="num rounded bg-sev-review/15 px-1.5 text-[11.5px] font-semibold text-sev-review">{Math.round(a.posts_per_day)} posts/day</span>}
                      <span className="num text-[12px] text-muted">{a.items} posts · {a.stories.length} narratives{a.created_at ? ` · created ${a.created_at.slice(0, 10)}` : ""}</span>
                    </div>
                    <ul className="mt-1.5 space-y-0.5 text-[13px]">
                      {a.evidence.map((e) => (
                        <li key={e.key} className="flex items-center gap-2">
                          <span className="inline-block h-1.5 rounded-full bg-sev-priority/70" style={{ width: `${Math.max(6, e.weight * 120)}px` }} />
                          <span>{e.text}</span>
                        </li>
                      ))}
                    </ul>
                    {a.family.length > 0 && (
                      <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[12px] text-muted">
                        Same group:
                        {a.family.map((p) => (
                          <button key={p.id} onClick={() => openAccount(p.id)} className="num rounded border border-line-strong px-1.5 hover:border-accent hover:text-accent">{p.label}</button>
                        ))}
                      </div>
                    )}
                    {a.partners.length > 0 && (
                      <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[12px] text-muted">
                        Posts with:
                        {a.partners.map((p) => (
                          <button key={p.id} onClick={() => openAccount(p.id)} className="num rounded border border-line-strong px-1.5 hover:border-accent hover:text-accent"
                            title={`${p.stories.length} narrative(s) together`}>{p.label}{p.stories.length > 1 ? ` ×${p.stories.length}` : ""}</button>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="text-right">
                    <div className="num text-[20px] font-semibold">{Math.round(a.score * 100)}</div>
                    <div className="text-[11px] text-muted">score</div>
                  </div>
                </li>
              ))}
            </ol>
          )}
          {rows.length > 15 && (
            <button onClick={() => setAll(!all)} className="w-full border-t border-line py-2 text-[13px] text-accent hover:bg-panel-2">
              {all ? "Show top 15" : `Show all ${rows.length}`}
            </button>
          )}
        </>
      )}
    </section>
  );
}
