"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { Empty } from "@/components/ui/kit";
import { isAdmin, useSession } from "@/lib/auth-client";

interface Point { text: string; refs: string[]; invalid_refs: string[] }
interface Result {
  investigator: Point[]; skeptic: Point[]; cost_usd: number; models: Record<string, string>;
  judge: { verdict?: string; confidence?: string; summary?: string; disarm?: { id: string; name: string }[]; key_evidence?: string[]; organic_hypotheses_tested?: string[] };
}

const VERDICT: Record<string, { label: string; color: string }> = {
  coordinated: { label: "Coordinated", color: "var(--sev-priority)" },
  suspicious: { label: "Suspicious", color: "var(--sev-review)" },
  organic: { label: "Organic", color: "var(--sev-organic)" },
  insufficient_evidence: { label: "Insufficient evidence", color: "var(--faint)" },
};

/** Débat Enquêteur ⇄ Sceptique puis verdict du Juge ; chaque référence [P#][A#][S#] renvoie à une preuve. */
export default function Investigation({ slug, storyId, onRef }: { slug: string; storyId: string; onRef: (ref: string) => void }) {
  const [res, setRes] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const admin = isAdmin(useSession().data?.user);
  const run = async () => {
    setBusy(true); setErr(null);
    try { setRes(await api<Result>(`/api/events/${slug}/stories/${storyId}/investigate`, { method: "POST" })); }
    catch (e) { setErr(String(e)); } finally { setBusy(false); }
  };
  if (!res) {
    return (
      <div className="flex items-center gap-4">
        <button onClick={run} disabled={busy} className="rounded-md bg-accent px-4 py-2 text-[13px] font-medium text-white disabled:opacity-60">
          {busy ? (admin ? "Agents are debating… (~20 s)" : "Loading…") : admin ? "Run the investigation" : "Show the AI investigation"}
        </button>
        <span className="text-[12.5px] text-muted">An investigator builds the case, a skeptic looks for organic explanations, a judge decides. Every point must cite the evidence below.
          {admin ? " ≈ $0.05, cached afterwards." : " Public demo: shows investigations already run, no new AI call."}</span>
        {err && <span className="text-[12.5px] text-sev-priority">{err}</span>}
      </div>
    );
  }
  const v = VERDICT[res.judge.verdict ?? ""] ?? VERDICT.insufficient_evidence;
  return (
    <div className="space-y-4">
      <div className="rounded-md border-l-4 bg-panel-2 p-4" style={{ borderColor: v.color }}>
        <div className="flex flex-wrap items-center gap-3">
          <span className="rounded-[3px] px-2 text-[12px] font-semibold uppercase leading-6 text-white" style={{ background: v.color }}>{v.label}</span>
          <span className="text-[12.5px] text-muted">confidence: <b className="text-text">{res.judge.confidence ?? "—"}</b></span>
          {res.judge.disarm?.map((t) => (
            <a key={t.id} href={`https://disarmframework.herokuapp.com/search?q=${t.id}`} target="_blank" rel="noreferrer"
              className="num rounded-[3px] border border-line-strong px-1.5 text-[11.5px] leading-5 text-muted hover:text-accent" title="DISARM technique">{t.id} · {t.name}</a>
          ))}
        </div>
        <p className="mt-2 text-[14px] leading-relaxed"><Refs text={res.judge.summary ?? ""} onRef={onRef} /></p>
        {!!res.judge.organic_hypotheses_tested?.length && (
          <div className="mt-2 text-[12.5px] text-muted">Organic explanations tested: {res.judge.organic_hypotheses_tested.join(" · ")}</div>
        )}
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <Column title="Investigator" hint="builds the coordination case" points={res.investigator} onRef={onRef} />
        <Column title="Skeptic" hint="looks for organic explanations" points={res.skeptic} onRef={onRef} />
      </div>
      <div className="text-[11.5px] text-faint">Models: {Object.entries(res.models).map(([k, m]) => `${k} ${m}`).join(" · ")} · cost ${res.cost_usd.toFixed(3)} · references are checked: invented ones are flagged.</div>
    </div>
  );
}

function Column({ title, hint, points, onRef }: { title: string; hint: string; points: Point[]; onRef: (r: string) => void }) {
  return (
    <div className="rounded-md border border-line bg-panel p-3">
      <div className="text-[13.5px] font-semibold">{title} <span className="font-normal text-faint">· {hint}</span></div>
      {points.length ? (
        <ul className="mt-2 space-y-2">
          {points.map((p, k) => (
            <li key={k} className="text-[13px] leading-snug">
              <Refs text={p.text} onRef={onRef} />
              {p.invalid_refs.length > 0 && <span className="ml-1 text-[11.5px] text-sev-priority">(unverified refs: {p.invalid_refs.join(", ")})</span>}
            </li>
          ))}
        </ul>
      ) : <Empty text="No point" />}
    </div>
  );
}

/** Rend les références [P3][A1][S2] cliquables. */
function Refs({ text, onRef }: { text: string; onRef: (r: string) => void }) {
  const parts = text.replace(/\*\*/g, "").split(/(\[[PAS]\d+\])/g);
  return (
    <>
      {parts.map((p, i) => {
        const m = p.match(/^\[([PAS]\d+)\]$/);
        return m ? (
          <button key={i} onClick={() => onRef(m[1])} className="num mx-0.5 rounded bg-[#eef3fd] px-1 text-[11.5px] text-accent hover:underline">{m[1]}</button>
        ) : <span key={i}>{p}</span>;
      })}
    </>
  );
}
