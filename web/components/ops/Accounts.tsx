"use client";
import { useMemo, useState } from "react";
import { passes, useOps } from "@/lib/store";
import { useView } from "@/lib/useView";
import { STANCE, getAccounts, type Account, type Stance } from "@/lib/views";
import { Empty, FlagChips, PlatformBadge } from "@/components/ui/kit";
import Suspects from "./Suspects";

type Key = "risk" | "stories" | "items" | "followers" | "created_at";

export default function Accounts({ slug }: { slug: string }) {
  const { data } = useView(() => getAccounts(slug), [slug]);
  const { filters, openAccount } = useOps();
  const [q, setQ] = useState("");
  const [onlyFlagged, setOnlyFlagged] = useState(false);
  const [sort, setSort] = useState<{ k: Key; desc: boolean }>({ k: "risk", desc: false });

  const rows = useMemo(() => {
    const rank = { high: 0, medium: 1, none: 2 } as const;
    const val = (a: Account): number | string => sort.k === "risk" ? rank[a.risk] : sort.k === "stories" ? a.stories.length
      : sort.k === "items" ? a.items : sort.k === "followers" ? (a.followers ?? -1) : (a.created_at ?? "");
    return (data ?? [])
      .filter((a) => passes(filters, { platform: a.platform }) && a.label.toLowerCase().includes(q.toLowerCase()) && (!onlyFlagged || a.flags.some((f) => f.risk !== "low")))
      .sort((a, b) => { const x = val(a), y = val(b); return (x < y ? -1 : x > y ? 1 : 0) * (sort.desc ? -1 : 1); });
  }, [data, filters, q, onlyFlagged, sort]);

  if (!data) return <div className="p-8"><Empty text="Loading accounts…" /></div>;
  const onSort = (k: Key) => setSort((s) => ({ k, desc: s.k === k ? !s.desc : k !== "risk" }));

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[1280px] p-6">
        <Suspects slug={slug} />
        <div className="mb-3 flex items-center gap-3">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search accounts and sources…"
            className="h-9 w-80 rounded-md border border-line-strong bg-panel px-3 text-[13.5px] outline-none focus:border-accent" />
          <label className="flex items-center gap-2 text-[13px]"><input type="checkbox" checked={onlyFlagged} onChange={(e) => setOnlyFlagged(e.target.checked)} />Only accounts with risk flags</label>
          <span className="num ml-auto text-[12.5px] text-muted">{rows.length} of {data.length}</span>
        </div>
        <table className="w-full overflow-hidden rounded-md border border-line bg-panel text-[13px]">
          <thead className="text-left text-[12px] text-muted">
            <tr className="border-b border-line">
              <th className="px-3 py-2 font-medium">Account / source</th><th className="font-medium">Platform</th>
              <H k="risk" sort={sort} onSort={onSort}>Risk flags</H><H k="stories" right sort={sort} onSort={onSort}>Narratives</H><H k="items" right sort={sort} onSort={onSort}>Posts</H>
              <th className="px-3 font-medium">Stance of its narratives</th><H k="followers" right sort={sort} onSort={onSort}>Followers</H><H k="created_at" sort={sort} onSort={onSort}>Created</H>
            </tr>
          </thead>
          <tbody>
            {rows.map((a) => (
              <tr key={a.id} onClick={() => openAccount(a.id)} className="cursor-pointer border-b border-line last:border-0 hover:bg-panel-2">
                <td className="num px-3 py-2 text-accent">{a.label}</td>
                <td><PlatformBadge p={a.platform} /></td>
                <td className="px-3"><FlagChips flags={a.flags} /></td>
                <td className="num px-3 text-right">{a.stories.length || <span className="text-faint">0</span>}</td>
                <td className="num px-3 text-right">{a.items}</td>
                <td className="px-3"><StanceMix mix={a.stance_mix} /></td>
                <td className="num px-3 text-right">{a.followers?.toLocaleString("en-US") ?? <span className="text-faint">n/a</span>}</td>
                <td className="num px-3">{a.created_at?.slice(0, 10) ?? <span className="text-faint">n/a</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function StanceMix({ mix }: { mix: Partial<Record<Stance, number>> }) {
  const entries = (Object.entries(mix) as [Stance, number][]).filter(([s]) => s !== "unclassified");
  const total = entries.reduce((a, [, n]) => a + n, 0);
  if (!total) return <span className="text-[12px] text-faint">—</span>;
  return (
    <span className="flex h-2 w-28 overflow-hidden rounded-full bg-line" title={entries.map(([s, n]) => `${STANCE[s].label}: ${n}`).join(" · ")}>
      {entries.map(([s, n]) => <span key={s} style={{ width: `${(n / total) * 100}%`, background: STANCE[s].color }} />)}
    </span>
  );
}

function H({ k, children, right, sort, onSort }: { k: Key; children: React.ReactNode; right?: boolean; sort: { k: Key; desc: boolean }; onSort: (k: Key) => void }) {
  return (
    <th className={`px-3 py-2 font-medium ${right ? "text-right" : ""}`}>
      <button onClick={() => onSort(k)} className="hover:text-text">{children}{sort.k === k ? (sort.desc ? " ↓" : " ↑") : ""}</button>
    </th>
  );
}
