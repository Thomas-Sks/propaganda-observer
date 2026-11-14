"use client";
import { useOps } from "@/lib/store";
import { useView } from "@/lib/useView";
import { STANCE, fmtTs, getAccount } from "@/lib/views";
import { Collapsible, Empty, FlagChips, PlatformBadge, SeverityBadge } from "@/components/ui/kit";
import { StanceMix } from "./Accounts";

/** Tiroir latéral : fiche d'un compte (indicateurs, histoires, publications). */
export default function AccountDrawer({ slug }: { slug: string }) {
  const { account, openAccount, openStory } = useOps();
  const { data: a } = useView(() => (account ? getAccount(slug, account) : Promise.resolve(null)), [slug, account]);
  if (!account) return null;
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/20" onClick={() => openAccount(null)}>
      <aside onClick={(e) => e.stopPropagation()} className="h-full w-[520px] overflow-y-auto border-l border-line bg-bg shadow-2xl">
        {!a || a.id !== account ? <div className="p-6"><Empty text="Loading…" /></div> : (
          <div className="space-y-4 p-5">
            <div className="flex items-center gap-2">
              <PlatformBadge p={a.platform} /><span className="num text-[16px] font-semibold">{a.label}</span>
              <button onClick={() => openAccount(null)} className="ml-auto rounded-md px-2 py-1 text-[13px] text-muted hover:bg-panel-2">Close ✕</button>
            </div>
            <div className="rounded-md border border-line bg-panel p-4">
              <div className="text-[12.5px] font-semibold text-muted">Risk flags</div>
              <div className="mt-1.5"><FlagChips flags={a.flags} /></div>
              <ul className="mt-2 space-y-0.5 text-[12.5px] text-muted">{a.flags.map((f) => <li key={f.key}><b className="text-text">{f.label}:</b> {f.detail}</li>)}</ul>
              <div className="num mt-3 grid grid-cols-3 gap-2 text-[12.5px]">
                <div><div className="text-muted">Posts</div><div className="text-[15px] font-semibold">{a.items}</div></div>
                <div><div className="text-muted">Followers</div><div className="text-[15px] font-semibold">{a.followers?.toLocaleString("en-US") ?? "n/a"}</div></div>
                <div><div className="text-muted">Created</div><div className="text-[15px] font-semibold">{a.created_at?.slice(0, 10) ?? "n/a"}</div></div>
              </div>
              <div className="mt-3 flex items-center gap-2 text-[12.5px] text-muted">Stance of its narratives <StanceMix mix={a.stance_mix} /></div>
            </div>
            <Collapsible title="Narratives" count={a.stories.length} defaultOpen>
              {a.stories.length ? a.stories.map((s) => (
                <button key={s} onClick={() => { openAccount(null); openStory(s); }} className="flex w-full items-start gap-2 py-1 text-left text-[13px] hover:text-accent">
                  <SeverityBadge level={a.story_info[s]?.level ?? "organic"} size="sm" />
                  <span className="shrink-0" style={{ color: STANCE[a.story_info[s]?.stance ?? "unclassified"].color }}>{STANCE[a.story_info[s]?.stance ?? "unclassified"].icon}</span>
                  <span className="line-clamp-2">{a.story_info[s]?.title ?? s}</span>
                </button>
              )) : <span className="text-[13px] text-faint">Not part of any narrative.</span>}
            </Collapsible>
            <Collapsible title="Publications" count={a.publications.length} defaultOpen>
              <ol className="divide-y divide-line">
                {a.publications.map((p) => (
                  <li key={p.uid} className="py-2">
                    <div className="flex items-center gap-2 text-[12px]"><span className="text-[11.5px] uppercase text-muted">{p.format}</span><span className="num text-muted">{fmtTs(p.ts)}</span>
                      {p.stance !== "unclassified" && <span style={{ color: STANCE[p.stance].color }}>{STANCE[p.stance].icon} {STANCE[p.stance].short}</span>}</div>
                    {p.url ? <a href={p.url} target="_blank" rel="noreferrer" className="mt-0.5 block text-[13px] leading-snug hover:text-accent">{p.text}</a>
                      : <div className="mt-0.5 text-[13px]">{p.text}</div>}
                  </li>
                ))}
              </ol>
            </Collapsible>
          </div>
        )}
      </aside>
    </div>
  );
}
