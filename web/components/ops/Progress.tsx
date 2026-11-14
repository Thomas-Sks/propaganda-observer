"use client";
import { useOps, type Step } from "@/lib/store";

const SOURCES = ["web", "youtube", "bluesky", "tiktok", "telegram", "networks", "instagram"];
const ANALYSIS = ["relevance", "narratives", "stance", "video"];

function Icon({ s }: { s: Step["state"] }) {
  if (s === "running") return <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-accent border-t-transparent" />;
  if (s === "done") return <span className="text-[12px] text-st-debunks">✓</span>;
  if (s === "error") return <span className="text-[12px] text-sev-priority">!</span>;
  if (s === "skipped") return <span className="text-[12px] text-faint">–</span>;
  return <span className="inline-block h-2 w-2 rounded-full bg-line-strong" />;
}

/** Bandeau de progression de la passe en cours (collecte par source puis analyse). */
export function ProgressStrip() {
  const p = useOps((s) => s.progress);
  if (!p) return null;
  const stopped = !!(p.pass as { stopped?: boolean }).stopped;
  const running = !stopped && (p.pass.state === "running" || p.steps.some((x) => x.state === "running"));
  const current = p.steps.find((x) => x.state === "running");
  return (
    <div className={`flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1 border-b border-line px-5 py-1.5 text-[12.5px] ${running ? "bg-[#eef3fd]" : "bg-panel"}`}>
      <span className="font-semibold">{stopped ? "Collection stopped: showing the data collected so far" : running ? `Working: ${current?.label ?? "starting"}…` : "Up to date"}</span>
      {p.steps.map((x) => (
        <span key={x.key} className="inline-flex items-center gap-1.5 text-muted" title={x.detail || x.state}>
          <Icon s={x.state} />{x.label}{x.state === "done" && x.count != null ? <span className="num text-text">{x.count}</span> : null}
        </span>
      ))}
      {!running && p.pass.next_at && <span className="ml-auto text-faint">next pass {new Date(p.pass.next_at).toISOString().slice(11, 16)}Z</span>}
    </div>
  );
}

/** Grand état d'attente tant que les premières narratives ne sont pas prêtes. */
export function FirstRun() {
  const p = useOps((s) => s.progress);
  const steps = p?.steps ?? [];
  const group = (keys: string[]) => steps.filter((x) => keys.includes(x.key));
  return (
    <div className="mx-auto mt-10 max-w-[720px] rounded-md border border-line bg-panel p-6">
      <div className="flex items-center gap-3">
        <span className="inline-block h-5 w-5 animate-spin rounded-full border-[3px] border-accent border-t-transparent" />
        <h2 className="text-[17px] font-semibold">Building the first picture of this narrative…</h2>
      </div>
      <p className="mt-2 text-[13.5px] text-muted">The first pass collects every platform, then groups and assesses what it found. It usually takes 2 to 5 minutes; this page updates by itself.</p>
      <div className="mt-4 grid gap-6 md:grid-cols-2">
        {[["Collecting", SOURCES], ["Analysing", ANALYSIS]].map(([title, keys]) => (
          <div key={title as string}>
            <div className="text-[12.5px] font-semibold text-muted">{title as string}</div>
            <ul className="mt-1.5 space-y-1.5">
              {group(keys as string[]).map((x) => (
                <li key={x.key} className="flex items-center gap-2 text-[13.5px]">
                  <span className="flex w-4 justify-center"><Icon s={x.state} /></span>
                  <span className={x.state === "pending" ? "text-faint" : ""}>{x.label}</span>
                  {x.state === "done" && x.count != null && <span className="num ml-auto text-muted">{x.count}</span>}
                  {x.state === "error" && <span className="ml-auto truncate text-[12px] text-sev-priority">{x.detail}</span>}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}
