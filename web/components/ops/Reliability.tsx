"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Collapsible, Empty } from "@/components/ui/kit";

/* Onglet Reliability : mesures de fiabilité des détecteurs (data/eval/results.json via GET /api/reliability).
   Système v2 : métriques en gris/encre (pas de couleur de sévérité), bleu réservé aux liens. */

export interface Metrics {
  confusion: { tp: number; fp: number; tn: number; fn: number };
  n: number; positives: number; negatives: number;
  precision: number | null; precision_ci: [number, number] | null;
  recall: number | null; recall_ci: [number, number] | null;
  fpr: number | null; fpr_ci: [number, number] | null;
  f1: number | null; auc?: number; auc_ci?: [number, number];
}
interface Dataset { name: string; url: string | null; n: number; positives: number; negatives: number; note: string }
interface Breakdown { label: string; kind: "recall" | "fpr"; n: number; rate: number; detail?: string }
interface ErrorCase { item: string; reason: string }
export interface Detector {
  id: string; name: string; question: string; method: string; threshold: string; split: string;
  datasets: Dataset[]; test: Metrics; train?: Metrics;
  baselines?: (Metrics & { name: string; threshold: string })[];
  breakdown: Breakdown[]; breakdown_title: string;
  errors: { false_positives: ErrorCase[]; false_negatives: ErrorCase[] };
  limits: string[];
  changelog?: { version: string; date: string; status: string; summary: string; domains: string[] }[];
}
export interface ReliabilityResults {
  version: string; generated_at: string; fpr_target: number; detectors: Detector[]; known_limits: string[];
}

const pct = (x: number | null | undefined, d = 1) => (x === null || x === undefined ? "n/a" : `${(100 * x).toFixed(d)}%`);
const ci = (c: [number, number] | null | undefined) => (c ? `95% CI ${pct(c[0])} – ${pct(c[1])}` : "undefined");

export default function Reliability({ data: initial }: { data?: ReliabilityResults }) {
  const [data, setData] = useState<ReliabilityResults | null>(initial ?? null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (initial) return;
    api<ReliabilityResults>("/api/reliability").then(setData).catch((e: Error) => setError(e.message));
  }, [initial]);

  if (error) return <div className="p-8"><Empty text={`Reliability results unavailable (${error}).`} /></div>;
  if (!data) return <div className="p-8"><Empty text="Loading reliability measurements…" /></div>;

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[1180px] space-y-6 p-6">
        <header className="space-y-2">
          <h1 className="text-[20px] font-semibold">Reliability</h1>
          <p className="max-w-[760px] text-[15px] leading-relaxed">
            We measure every detector on labelled data it never saw while tuning. Below: precision, recall and
            the <b>false-positive rate</b> at the threshold we actually use, with 95% confidence intervals, and the
            cases we get wrong.
          </p>
          <p className="text-[12.5px] text-muted">
            Target: false-positive rate ≤ <span className="num">{pct(data.fpr_target, 0)}</span> · version{" "}
            <span className="num">{data.version}</span> · measured{" "}
            <span className="num">{data.generated_at.slice(0, 16).replace("T", " ")} UTC</span> · scores rank what to
            check first; they never prove that an account or a source is malicious.
          </p>
        </header>

        <Overview detectors={data.detectors} />

        {data.detectors.map((d) => <DetectorCard key={d.id} d={d} />)}

        <section className="rounded-md border border-line-strong bg-panel px-5 py-4">
          <h2 className="mb-2 text-[15px] font-semibold">Known limits</h2>
          <ul className="list-disc space-y-1 pl-5 text-[13.5px] text-muted">
            {data.known_limits.map((l) => <li key={l}>{l}</li>)}
          </ul>
        </section>
      </div>
    </div>
  );
}

/* Tableau de synthèse : une ligne par détecteur, les trois chiffres clés */
function Overview({ detectors }: { detectors: Detector[] }) {
  return (
    <table className="w-full overflow-hidden rounded-md border border-line bg-panel text-[13px]">
      <thead className="text-left text-[12px] text-muted">
        <tr className="border-b border-line">
          <th className="px-4 py-2 font-medium">Detector</th>
          <th className="px-3 text-right font-medium">Precision</th>
          <th className="px-3 text-right font-medium">Recall</th>
          <th className="px-3 text-right font-medium">FPR</th>
          <th className="hidden px-4 text-right font-medium sm:table-cell">Test cases</th>
        </tr>
      </thead>
      <tbody>
        {detectors.map((d) => (
          <tr key={d.id} className="border-b border-line last:border-0">
            <td className="px-4 py-2"><a href={`#rel-${d.id}`} className="text-accent hover:underline">{d.name}</a></td>
            <td className="num px-3 text-right">{pct(d.test.precision)}</td>
            <td className="num px-3 text-right">{pct(d.test.recall)}</td>
            <td className="num px-3 text-right font-semibold">{pct(d.test.fpr)}</td>
            <td className="num hidden px-4 text-right sm:table-cell">{d.test.n.toLocaleString("en-US")}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function DetectorCard({ d }: { d: Detector }) {
  const t = d.test;
  const c = t.confusion;
  return (
    <section id={`rel-${d.id}`} className="scroll-mt-4 rounded-md border border-line bg-panel">
      <div className="border-b border-line px-5 py-4">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h2 className="text-[17px] font-semibold">{d.name}</h2>
          <span className="text-[13.5px] text-muted">{d.question}</span>
        </div>
        <div className="mt-2 flex flex-wrap gap-2 text-[12px]">
          <Tag label="Threshold" value={d.threshold} />
          <Tag label="Test set" value={`${t.positives.toLocaleString("en-US")} positives · ${t.negatives.toLocaleString("en-US")} negatives`} />
        </div>
      </div>

      <div className="grid gap-5 px-5 py-4 lg:grid-cols-[1fr_260px]">
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Metric label="Precision" help="Of what we flag, how much is truly positive" value={t.precision} ciV={t.precision_ci}
              frac={`${c.tp} / ${c.tp + c.fp}`} />
            <Metric label="Recall" help="Of the true positives, how many we catch" value={t.recall} ciV={t.recall_ci}
              frac={`${c.tp} / ${c.tp + c.fn}`} />
            <Metric label="False-positive rate" help="Of the legitimate cases, how many we wrongly flag" value={t.fpr}
              ciV={t.fpr_ci} frac={`${c.fp} / ${c.fp + c.tn}`} strong />
            <Metric label={t.auc !== undefined ? "F1 · AUC" : "F1"} help="Harmonic mean of precision and recall"
              value={t.f1} sub={t.auc !== undefined ? `AUC ${t.auc.toFixed(3)} (${t.auc_ci?.map((x) => x.toFixed(3)).join("–")})` : undefined} />
          </div>

          <div>
            <h3 className="mb-2 text-[13px] font-semibold">{d.breakdown_title}</h3>
            <Breakdowns rows={d.breakdown} />
          </div>

          {d.baselines && d.baselines.length > 0 && (
            <div>
              <h3 className="mb-2 text-[13px] font-semibold">Same test set, other approaches</h3>
              <table className="w-full text-[12.5px]">
                <thead className="text-left text-[11.5px] text-muted">
                  <tr className="border-b border-line">
                    <th className="py-1 font-medium">Approach</th><th className="font-medium">Threshold</th>
                    <th className="text-right font-medium">Precision</th><th className="text-right font-medium">Recall</th>
                    <th className="text-right font-medium">FPR</th><th className="text-right font-medium">AUC</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-b border-line">
                    <td className="py-1.5 font-medium">{d.name} (shown above)</td><td className="text-muted">{d.threshold}</td>
                    <td className="num text-right">{pct(t.precision)}</td><td className="num text-right">{pct(t.recall)}</td>
                    <td className="num text-right">{pct(t.fpr)}</td><td className="num text-right">{t.auc?.toFixed(3) ?? "—"}</td>
                  </tr>
                  {d.baselines.map((b) => (
                    <tr key={b.name} className="border-b border-line last:border-0">
                      <td className="py-1.5">{b.name}</td><td className="text-muted">{b.threshold}</td>
                      <td className="num text-right">{pct(b.precision)}</td><td className="num text-right">{pct(b.recall)}</td>
                      <td className="num text-right" title={ci(b.fpr_ci)}>{pct(b.fpr)}</td>
                      <td className="num text-right">{b.auc?.toFixed(3) ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <aside className="space-y-4">
          <Confusion c={c} />
          <div>
            <h3 className="mb-1 text-[12px] font-semibold uppercase tracking-[0.04em] text-muted">Data</h3>
            <ul className="space-y-2 text-[12.5px]">
              {d.datasets.map((ds) => (
                <li key={ds.name}>
                  {ds.url ? <a href={ds.url} target="_blank" rel="noreferrer" className="text-accent hover:underline">{ds.name}</a>
                    : <span className="font-medium">{ds.name}</span>}
                  <span className="num text-muted"> · n={ds.n.toLocaleString("en-US")}</span>
                  <div className="text-faint">{ds.note}</div>
                </li>
              ))}
            </ul>
          </div>
        </aside>
      </div>

      <div className="space-y-2 border-t border-line px-5 py-4">
        <p className="text-[13px] text-muted"><span className="font-semibold text-text">How it works. </span>{d.method}</p>
        <p className="text-[13px] text-muted"><span className="font-semibold text-text">Split. </span>{d.split}</p>
        {d.changelog && d.changelog.length > 0 && (
          <div className="rounded-md border border-line bg-panel-2 px-3 py-2">
            <div className="mb-1 text-[12px] font-semibold uppercase tracking-[0.04em] text-muted">What this bench caught</div>
            <ul className="space-y-1 text-[13px]">
              {d.changelog.map((c) => (
                <li key={c.version}>
                  <span className="num font-semibold">{c.version}</span>
                  <span className="text-faint"> · {c.date} · {c.status}</span> — <span className="text-muted">{c.summary}</span>
                  {c.domains.length > 0 && <span className="num text-muted"> ({c.domains.join(", ")})</span>}
                </li>
              ))}
            </ul>
          </div>
        )}
        {d.limits.length > 0 && (
          <ul className="list-disc space-y-0.5 pl-5 text-[13px] text-muted">
            {d.limits.map((l) => <li key={l}>{l}</li>)}
          </ul>
        )}
      </div>

      <div className="grid gap-3 px-5 pb-5 md:grid-cols-2">
        <ErrorList title="False positives" hint="legitimate, but flagged" list={d.errors.false_positives}
          none="No false positive on this test set." />
        <ErrorList title="False negatives" hint="positive, but missed" list={d.errors.false_negatives}
          none="No false negative on this test set." />
      </div>
    </section>
  );
}

function Tag({ label, value }: { label: string; value: string }) {
  return (
    <span className="rounded-[3px] border border-line-strong px-2 leading-6">
      <span className="text-muted">{label}: </span><span className="font-medium">{value}</span>
    </span>
  );
}

function Metric({ label, value, ciV, frac, help, sub, strong }: {
  label: string; value: number | null; ciV?: [number, number] | null; frac?: string; help: string; sub?: string; strong?: boolean;
}) {
  return (
    <div className={`rounded-md border px-3 py-2.5 ${strong ? "border-text" : "border-line"}`} title={help}>
      <div className="text-[12px] text-muted">{label}</div>
      <div className="num mt-1 text-[22px] font-semibold leading-none">{pct(value)}</div>
      {ciV !== undefined && <div className="num mt-1.5 text-[11px] text-muted">{ci(ciV)}</div>}
      {frac && <div className="num text-[11px] text-faint">{frac}</div>}
      {sub && <div className="num mt-1.5 text-[11px] text-muted">{sub}</div>}
    </div>
  );
}

/* Matrice de confusion : intensité de gris proportionnelle à l'effectif (aucune couleur de sévérité) */
function Confusion({ c }: { c: Metrics["confusion"] }) {
  const max = Math.max(1, c.tp, c.fp, c.tn, c.fn);
  const cell = (v: number, label: string) => (
    <div className="flex flex-col items-center justify-center rounded-[3px] py-2"
      style={{ background: `color-mix(in srgb, var(--muted) ${Math.round((v / max) * 35)}%, var(--panel-2))` }}
      title={`${label}: ${v}`}>
      <span className="num text-[16px] font-semibold">{v.toLocaleString("en-US")}</span>
      <span className="text-[10.5px] text-muted">{label}</span>
    </div>
  );
  return (
    <div>
      <h3 className="mb-1 text-[12px] font-semibold uppercase tracking-[0.04em] text-muted">Confusion matrix (test)</h3>
      <div className="grid grid-cols-[64px_1fr_1fr] gap-1 text-[11px]">
        <span /><span className="text-center text-muted">Flagged</span><span className="text-center text-muted">Not flagged</span>
        <span className="self-center text-muted">Positive</span>{cell(c.tp, "true pos.")}{cell(c.fn, "missed")}
        <span className="self-center text-muted">Legitimate</span>{cell(c.fp, "false alarm")}{cell(c.tn, "true neg.")}
      </div>
    </div>
  );
}

/* Barres horizontales simples : une seule série, encre neutre ; les lignes « FPR » sont libellées comme telles */
function Breakdowns({ rows }: { rows: Breakdown[] }) {
  return (
    <ul className="space-y-1.5">
      {rows.map((b) => (
        <li key={b.label} className="grid grid-cols-[minmax(0,300px)_1fr_64px] items-center gap-3 text-[12.5px]"
          title={`${b.detail ? b.detail + " — " : ""}${b.kind === "fpr" ? "flagged (false alarms)" : "caught"}: ${pct(b.rate)} of ${b.n}`}>
          <span className="truncate">
            {b.label}
            <span className="text-faint"> · {b.kind === "fpr" ? "false alarms" : "caught"}</span>
          </span>
          <span className="h-2 rounded-full bg-line">
            <span className={`block h-2 rounded-full ${b.kind === "fpr" ? "bg-muted" : "bg-text"}`}
              style={{ width: `${Math.max(b.rate > 0 ? 1 : 0, b.rate * 100)}%` }} />
          </span>
          <span className="num text-right">{pct(b.rate, 0)} <span className="text-faint">/{b.n}</span></span>
        </li>
      ))}
    </ul>
  );
}

function ErrorList({ title, hint, list, none }: { title: string; hint: string; list: ErrorCase[]; none: string }) {
  return (
    <Collapsible title={title} hint={hint} count={list.length}>
      {list.length === 0 ? <p className="text-[13px] text-muted">{none}</p> : (
        <ul className="divide-y divide-line">
          {list.map((e, k) => (
            <li key={k} className="py-2">
              <div className="text-[13px]">{e.item}</div>
              <div className="mt-0.5 text-[12.5px] text-muted">{e.reason}</div>
            </li>
          ))}
        </ul>
      )}
    </Collapsible>
  );
}
