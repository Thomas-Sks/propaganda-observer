"use client";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useEventStream } from "@/lib/stream";
import { useOps, type Tab } from "@/lib/store";
import { api } from "@/lib/api";
import { PLATFORM_NAME, SEVERITY, STANCE, type Severity, type Stance } from "@/lib/views";
import Brief from "./Brief";
import Stories from "./Stories";
import Accounts from "./Accounts";
import Themes from "./Themes";
import AccountDrawer from "./AccountDrawer";
import { ProgressStrip } from "./Progress";
import UserMenu from "@/components/ui/UserMenu";
import { PublishButton, PublishedBadge } from "./Publish";
import { isAdmin, useSession } from "@/lib/auth-client";

const NetworkView = dynamic(() => import("./NetworkView"), { ssr: false });
const Coordination = dynamic(() => import("./Coordination"), { ssr: false });

const TABS: { id: Tab; label: string; hint: string }[] = [
  { id: "brief", label: "Brief", hint: "The campaign, its activity over time, what to review first" },
  { id: "stories", label: "Narratives", hint: "Each narrative: verdict, why, spread, evidence" },
  { id: "network", label: "Network", hint: "Which accounts push the same narratives" },
  { id: "coordination", label: "Coordination", hint: "Accounts that act together: same text, link or hashtags within seconds" },
  { id: "themes", label: "Themes", hint: "What is being pushed, by whom, in which language, over time" },
  { id: "accounts", label: "Accounts", hint: "Every account and source, with risk flags" },
];

export default function OpsRoom({ slug, label }: { slug: string; label: string }) {
  const session = useSession();
  const admin = isAdmin(session.data?.user);
  const demo = !session.isPending && !admin;
  useEventStream(slug, admin);
  const { tab, setTab, connected, status, progress } = useOps();
  const stopped = !!(progress?.pass as { stopped?: boolean } | undefined)?.stopped;
  return (
    <div className="flex h-screen flex-col">
      <header className="flex h-14 shrink-0 items-center gap-4 bg-navy px-5 text-white">
        <Link href="/" className="text-[15px] font-bold tracking-[0.08em]">OBSERVER</Link>
        <span className="h-5 w-px bg-white/25" />
        <span className="truncate text-[15px] font-medium">{label}</span>
        {demo ? <span className="ml-auto"><PublishedBadge slug={slug} /></span> : (
          <span className="ml-auto flex items-center gap-2 text-[12.5px] text-white/75">
            <span className={`h-2 w-2 rounded-full ${stopped ? "bg-white/50" : connected ? "live-dot bg-[#4ade80]" : "bg-sev-priority"}`} />{stopped ? "Stopped" : connected ? (status || "Live") : "Reconnecting…"}
          </span>
        )}
        <Link href="/trust" className="text-[13px] text-white/80 hover:text-white">Trust card</Link>
        <Link href="/reliability" className="text-[13px] text-white/80 hover:text-white">Reliability</Link>
        {admin && <button onClick={() => api(`/api/events/${slug}/start`, { method: "POST" })}
          className="rounded-md bg-accent px-3 py-1.5 text-[12.5px] font-semibold text-white hover:brightness-110">Refresh now</button>}
        {admin && <PublishButton slug={slug} />}
        <UserMenu />
      </header>
      <nav className="flex h-12 shrink-0 items-stretch gap-1 border-b border-line bg-panel px-3 shadow-sm">
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)} title={t.hint}
            className={`border-b-[3px] px-5 text-[15px] ${tab === t.id ? "border-accent font-bold text-accent" : "border-transparent font-medium text-muted hover:text-text"}`}>
            {t.label}
          </button>
        ))}
      </nav>
      {!demo && <ProgressStrip />}
      <FilterBar />
      <div className="min-h-0 flex-1">
        {tab === "brief" && <Brief slug={slug} />}
        {tab === "stories" && <Stories slug={slug} />}
        {tab === "network" && <NetworkView slug={slug} />}
        {tab === "coordination" && <Coordination slug={slug} />}
        {tab === "themes" && <Themes slug={slug} />}
        {tab === "accounts" && <Accounts slug={slug} />}
      </div>
      <AccountDrawer slug={slug} />
    </div>
  );
}

/** Filtres globaux, persistants d'un onglet à l'autre. */
function FilterBar() {
  const { filters, toggle, clearFilters } = useOps();
  const any = filters.platforms.length + filters.stances.length + filters.severities.length > 0;
  const Chip = ({ on, onClick, children, color }: { on: boolean; onClick: () => void; children: React.ReactNode; color?: string }) => (
    <button onClick={onClick} className={`rounded-full border px-2.5 py-0.5 text-[12.5px] ${on ? "border-accent bg-[#eef3fd] text-accent" : "border-line-strong text-muted hover:text-text"}`}>
      {color && <span className="mr-1" style={{ color }}>●</span>}{children}
    </button>
  );
  return (
    <div className="flex shrink-0 flex-wrap items-center gap-x-5 gap-y-2 border-b border-line bg-panel-2 px-5 py-2">
      <span className="text-[12px] font-semibold uppercase tracking-[0.05em] text-muted">Filters</span>
      <span className="flex flex-wrap items-center gap-1.5">
        {Object.keys(PLATFORM_NAME).filter((p) => !["x", "mastodon", "facebook"].includes(p)).map((p) => (
          <Chip key={p} on={filters.platforms.includes(p)} onClick={() => toggle("platforms", p)}>{PLATFORM_NAME[p]}</Chip>
        ))}
      </span>
      <span className="flex items-center gap-1.5">
        {(["promotes", "debunks", "neutral"] as Stance[]).map((s) => (
          <Chip key={s} on={filters.stances.includes(s)} onClick={() => toggle("stances", s)} color={STANCE[s].color}>{STANCE[s].short}</Chip>
        ))}
      </span>
      <span className="flex items-center gap-1.5">
        {(["priority", "review", "organic"] as Severity[]).map((s) => (
          <Chip key={s} on={filters.severities.includes(s)} onClick={() => toggle("severities", s)} color={SEVERITY[s].color}>{SEVERITY[s].label}</Chip>
        ))}
      </span>
      {any && <button onClick={clearFilters} className="text-[12.5px] text-accent hover:underline">Clear</button>}
    </div>
  );
}
