"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Collapsible, SeverityBadge } from "@/components/ui/kit";
import { SEVERITY } from "@/lib/views";
import { getProvenance, type Ev, type ProvFeature, type Provenance } from "@/lib/provenance";

// Exemples variés (pays, catégories) : le moteur est généraliste, aucun réseau ni pays n'est codé en dur
const EXAMPLES: { target: string; hint: string }[] = [
  { target: "thewashingtonexaminer.net", hint: "domain registered 11 days ago, imitates a US outlet" },
  { target: "globaltimes.cn", hint: "listed state media (CN)" },
  { target: "francais.news-pravda.com", hint: "listed influence network" },
  { target: "thehindu.com", hint: "established outlet (IN)" },
  { target: "abc.net.au", hint: "established public broadcaster (AU)" },
  { target: "tagesschau.de", hint: "established public broadcaster (DE)" },
];

/* Libellés courts pour la cascade (le libellé complet reste au survol et dans « Evidence ») */
const SHORT: Record<string, string> = {
  listed_network: "Listed source / network", shared_tracker: "Shared analytics ID", cloned_content: "Cloned content",
  typosquat: "Look-alike of a news outlet", young_domain: "Young domain (< 6 months)", no_transparency: "No about / legal / bylines",
  ai_text_share: "AI-generated text share", few_archives: "Few Wayback captures", amplified_by_cluster: "Amplified by a coordinated cluster",
  whois_masked: "WHOIS masked", cites_listed: "Cites listed sources", copied_posts: "Copied posts",
  in_coordinated_cluster: "In a coordinated cluster", automated: "Automated account", new_account: "New account", low_audience: "Low audience",
};
const bandColor = (b: string) => SEVERITY[b]?.color ?? "var(--faint)";
const day = (s?: string | null) => (s ? s.slice(0, 10) : "—");
const wb = (s?: string | null) => (s ? `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}` : "—");

/** Résumé lisible de la preuve brute d'une feature (affiché au survol et dans « Evidence »). */
function evidenceLine(f: ProvFeature): string {
  const e: NonNullable<Ev> = f.evidence ?? {};
  if (f.missing) return f.why_missing ?? "Not measured";
  switch (f.key) {
    case "listed_network":
      return e.list ? `${e.list} (lists frozen ${e.lists_frozen})` : e.detail ?? `Not on the lists (frozen ${e.lists_frozen ?? "—"})`;
    case "shared_tracker":
      return e.matches?.length
        ? e.matches.map((m: Ev) => `${m?.id} also on ${m?.domain}`).join(" · ")
        : `IDs found: ${e.ids?.length ? e.ids.join(", ") : "none"} · none shared with ${e.compared_with} listed sites`;
    case "cloned_content":
      return `${e.cloned}/${e.n} texts copied from an earlier listed source (${Math.round((e.share ?? 0) * 1000) / 10} %)` +
        (e.pairs?.[0] ? ` · e.g. from ${e.pairs[0].source}, Jaccard ${e.pairs[0].jaccard}` : "");
    case "typosquat": {
      const l = e.lookalike_of;
      const twins = e.registered_lookalikes;
      const t = twins ? ` · ${twins.n_registered} registered look-alikes of this domain` : "";
      return l ? `Imitates ${l.name ?? l.media} — ${l.media}${l.country ? `, ${l.country}` : ""} (${l.method}: ${l.detail})${t}` : `Not a look-alike of the ~90 major outlets in the registry${t}`;
    }
    case "young_domain":
      return `Registered ${day(e.registered)}${e.age_days?.rdap != null ? ` (${e.age_days.rdap} days ago)` : ""} · ` +
        `registrar ${e.registrar ?? "—"} · first certificate ${day(e.first_certificate)} · source ${e.source ?? "—"}`;
    case "no_transparency": {
      const found = [e.about_link && "about page", e.legal_link && "legal page", e.authors_marker && "author bylines"].filter(Boolean);
      return (found.length ? `Found: ${found.join(", ")}` : "No about page, legal notice or byline found") +
        (e.via === "wayback" ? ` (Wayback snapshot ${wb(e.snapshot)}: site unreachable live)` : "") +
        (e.offsite_about_or_legal?.length ? ` · about/legal links point to another domain: ${e.offsite_about_or_legal[0]}` : "");
    }
    case "few_archives":
      return `${e.captures >= e.capped_at ? `≥ ${e.capped_at}` : e.captures} daily captures · first ${wb(e.first_capture)}`;
    case "amplified_by_cluster":
      return `${e.n_clusters} coordinated cluster(s) link to it · ${e.items_linking} posts in the event link to it`;
    case "whois_masked":
      return `Registrant: ${e.registrant ?? "hidden"} (${e.source})`;
    case "cites_listed":
      return `${e.posts_citing_listed}/${e.posts} posts link to listed sources` + (e.examples?.[0] ? ` · e.g. ${e.examples[0].domain}` : "");
    case "copied_posts":
      return e.copypasta_clusters?.length ? `In ${e.copypasta_clusters.length} copypasta cluster(s)` : "No copied posts";
    case "in_coordinated_cluster":
      return e.clusters?.length ? `${e.clusters.length} cluster(s): ${e.clusters.map((c: Ev) => c?.level).join(", ")}` : "No coordinated cluster";
    default:
      return e.detail ?? e.label ?? JSON.stringify(e).slice(0, 160);
  }
}

export default function TrustCard({ initial }: { initial: string }) {
  const router = useRouter();
  const [q, setQ] = useState(initial);
  const [data, setData] = useState<Provenance | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ctl = useRef<AbortController | null>(null);

  const run = useCallback(async (target: string, push = true) => {
    const t = target.trim();
    if (!t) return;
    ctl.current?.abort();
    const c = new AbortController();
    ctl.current = c;
    setQ(t); setLoading(true); setError(null); setData(null);
    if (push) router.replace(`/trust?target=${encodeURIComponent(t)}`, { scroll: false });
    try {
      setData(await getProvenance(t, c.signal));
    } catch (e) {
      if (!c.signal.aborted) setError(String(e));
    } finally {
      if (!c.signal.aborted) setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    if (!initial) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- chargement initial depuis l'URL partagée
    void run(initial, false);
  }, [initial, run]);

  return (
    <div className="mx-auto w-full max-w-[1080px] px-6 py-8">
      <header className="mb-6 flex items-baseline gap-3">
        <Link href="/" className="text-[13px] text-faint hover:text-accent">Propaganda Observer</Link>
        <span className="text-faint">/</span>
        <h1 className="text-[20px] font-semibold">Trust card</h1>
        <span className="ml-auto text-[12.5px] text-faint">Provenance score · API <code className="num">GET /v1/provenance</code></span>
      </header>

      <form onSubmit={(e) => { e.preventDefault(); void run(q); }} className="flex gap-2">
        <input value={q} onChange={(e) => setQ(e.target.value)} aria-label="Target"
          placeholder="Paste a URL, a domain or an account (platform:id)"
          className="h-11 flex-1 rounded-md border border-line-strong bg-panel px-3 text-[15px] outline-none focus:border-accent" />
        <button type="submit" disabled={loading || !q.trim()}
          className="h-11 rounded-md bg-accent px-5 text-[14px] font-semibold text-white disabled:opacity-50">
          {loading ? "Checking…" : "Score"}
        </button>
      </form>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-[12.5px]">
        <span className="text-faint">Try:</span>
        {EXAMPLES.map((x) => (
          <button key={x.target} type="button" onClick={() => void run(x.target)} title={x.hint}
            className="rounded-[3px] border border-line bg-panel px-2 py-0.5 text-muted hover:border-accent hover:text-accent">
            <span className="num">{x.target}</span>
          </button>
        ))}
      </div>

      <div className="mt-6">
        {loading && (
          <div className="rounded-md border border-line bg-panel p-6 text-[13.5px] text-muted">
            <span className="live-dot mr-2 inline-block h-2 w-2 rounded-full bg-accent" />
            Checking RDAP / WHOIS, crt.sh, Wayback Machine, home page, look-alike domains and the event data… (first run up to ~30 s, then cached 7 days)
          </div>
        )}
        {error && <div className="rounded-md border border-sev-priority bg-panel p-4 text-[13px] text-sev-priority">{error}</div>}
        {data && !loading && <Card d={data} />}
      </div>
    </div>
  );
}

function Card({ d }: { d: Provenance }) {
  if (d.error) {
    return <div className="rounded-md border border-dashed border-line-strong bg-panel p-8 text-center text-[13.5px] text-muted">{d.error}</div>;
  }
  const color = bandColor(d.band);
  const shown = d.score ?? d.partial_score ?? 0;
  const facts = d.kind === "domain" ? domainFacts(d) : [];
  return (
    <div className="space-y-4">
      <div className="grid gap-4 rounded-md border border-line bg-panel p-5 md:grid-cols-[240px_1fr]">
        <div className="flex flex-col items-start gap-2 border-line md:border-r md:pr-5">
          <div className="text-[12.5px] text-muted">Provenance risk</div>
          <div className="flex items-baseline gap-1">
            <span className="num text-[64px] font-semibold leading-none" style={{ color: d.abstain ? "var(--faint)" : color }}>
              {d.abstain ? "—" : Math.round(shown)}
            </span>
            <span className="num text-[16px] text-faint">/100</span>
          </div>
          <SeverityBadge level={d.band} />
          <ScaleBar score={d.abstain ? null : shown} />
          {d.abstain && (
            <p className="text-[12.5px] text-muted">
              Insufficient data: {d.missing?.length} features missing (max 3). Partial score {d.partial_score} shown for reference only.
            </p>
          )}
        </div>
        <div className="min-w-0">
          <div className="flex flex-wrap items-baseline gap-2">
            <h2 className="num break-all text-[20px] font-semibold">{d.subject}</h2>
            <span className="rounded-[3px] border border-line-strong px-1.5 text-[11px] uppercase tracking-wide text-muted">{d.kind}</span>
            {d.registrable && d.registrable !== d.subject && <span className="text-[12.5px] text-faint">registrable domain <span className="num">{d.registrable}</span></span>}
          </div>
          <p className="mt-2 text-[13.5px] font-medium" style={{ color: "var(--text)" }}>
            {d.disclaimer} <span className="font-normal text-muted">A high score means “check first”, never “propaganda”.</span>
          </p>
          {facts.length > 0 && (
            <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1.5 text-[13px] sm:grid-cols-3">
              {facts.map(([k, v]) => (
                <div key={k} className="min-w-0"><dt className="text-[12px] text-faint">{k}</dt><dd className="num truncate" title={v}>{v}</dd></div>
              ))}
            </dl>
          )}
        </div>
      </div>

      <div className="rounded-md border border-line bg-panel p-5">
        <div className="mb-3 flex items-baseline gap-3">
          <h3 className="text-[15px] font-semibold">What pushes the score</h3>
          <span className="text-[12.5px] text-faint">Each bar adds its share of the risk; hover for the raw evidence</span>
        </div>
        <Waterfall d={d} />
      </div>

      <Collapsible title="Evidence" hint="raw outputs of the deterministic tools" count={d.features.length} defaultOpen>
        <ul className="divide-y divide-line">
          {d.features.map((f) => (
            <li key={f.key} className="grid grid-cols-[1fr_auto] gap-3 py-2.5">
              <div className="min-w-0">
                <div className="text-[13.5px] font-medium">{f.label}</div>
                <div className="break-words text-[12.5px] text-muted">{evidenceLine(f)}</div>
                <EvidenceLinks f={f} />
              </div>
              <div className="num self-start text-right text-[12.5px]">
                {f.missing ? <span className="text-faint">not measured</span>
                  : <span className={f.contribution ? "font-semibold text-text" : "text-faint"}>x={f.value} · {f.contribution ? `+${f.contribution}` : "0"}</span>}
              </div>
            </li>
          ))}
        </ul>
      </Collapsible>

      <Collapsible title="Method & weights" hint={d.method.model}>
        <p className="num mb-3 text-[13px]">{d.method.formula} · β₀ = {d.method.bias} (base {d.base_points} / 100)</p>
        <table className="w-full text-[13px]">
          <thead><tr className="text-left text-[12px] text-faint"><th className="py-1 font-normal">Feature</th><th className="py-1 text-right font-normal">Weight βᵢ</th></tr></thead>
          <tbody className="divide-y divide-line">
            {Object.entries(d.method.weights).map(([k, w]) => (
              <tr key={k}><td className="py-1.5">{w.label} <span className="num text-[11.5px] text-faint">{k}</span></td><td className="num py-1.5 text-right">+{w.weight.toFixed(1)}</td></tr>
            ))}
          </tbody>
        </table>
        <ul className="mt-3 space-y-1 text-[12.5px] text-muted">
          <li>Bands: {Object.entries(d.method.bands).map(([k, v]) => `${SEVERITY[k]?.label ?? k} ${v}`).join(" · ")}</li>
          <li>Abstention: {d.method.abstention}</li>
          <li>Calibration: {d.method.calibration}</li>
        </ul>
      </Collapsible>

      <Collapsible title="Limits" count={d.limits.length}>
        <ul className="list-disc space-y-1 pl-5 text-[13px] text-muted">{d.limits.map((l) => <li key={l}>{l}</li>)}</ul>
      </Collapsible>

      <p className="num text-[11.5px] text-faint">
        Model {d.model_version} · lists frozen {d.lists_frozen} · computed {d.computed_at.slice(0, 19).replace("T", " ")} UTC
      </p>
    </div>
  );
}

function domainFacts(d: Provenance): [string, string][] {
  const s = d.signals ?? {};
  const reg = s.registration ?? {};
  const home = s.homepage ?? {};
  const typo = d.features.find((f) => f.key === "typosquat")?.evidence?.registered_lookalikes;
  return [
    ["Registered", reg.created ? `${day(reg.created)} (${reg.source})` : "unknown"],
    ["Registrar", reg.registrar ?? "—"],
    ["First certificate", s.crt?.first_cert ? day(s.crt.first_cert) : s.crt ? "none" : "crt.sh timeout"],
    ["First Wayback capture", wb(s.wayback?.first_capture)],
    ["Analytics / ad IDs", home.trackers?.length ? home.trackers.join(", ") : home.error ? "page unreachable" : "none"],
    ["Registered look-alikes", typo ? `${typo.n_registered}${typo.complete ? "" : "+"}` : "—"],
  ];
}

function EvidenceLinks({ f }: { f: ProvFeature }) {
  const e = f.evidence ?? {};
  const links: [string, string][] = [];
  if (f.key === "cloned_content") for (const p of e.pairs ?? []) if (p.url && p.source_url) links.push([`copy → source (${p.jaccard})`, p.source_url]);
  if (f.key === "typosquat") for (const t of (e.registered_lookalikes?.registered ?? []).slice(0, 8)) links.push([t, `https://${t}`]);
  if (!links.length) return null;
  return (
    <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[12px]">
      {links.map(([l, u]) => <a key={l + u} href={u} target="_blank" rel="noreferrer noopener" className="num text-accent hover:underline">{l}</a>)}
    </div>
  );
}

function ScaleBar({ score }: { score: number | null }) {
  return (
    <div className="mt-1 w-full">
      <div className="relative flex h-2 w-full overflow-hidden rounded-full">
        <div className="h-full" style={{ width: "40%", background: "var(--sev-organic)", opacity: 0.35 }} />
        <div className="h-full" style={{ width: "30%", background: "var(--sev-review)", opacity: 0.35 }} />
        <div className="h-full" style={{ width: "30%", background: "var(--sev-priority)", opacity: 0.35 }} />
        {score != null && <div className="absolute top-[-2px] h-3 w-[3px] rounded bg-text" style={{ left: `calc(${score}% - 1px)` }} />}
      </div>
      <div className="num mt-0.5 flex justify-between text-[10.5px] text-faint"><span>0</span><span>40</span><span>70</span><span>100</span></div>
    </div>
  );
}

/** Cascade horizontale : base σ(β₀), puis chaque feature ajoute sa part, jusqu'au score final (couleur = sévérité). */
function Waterfall({ d }: { d: Provenance }) {
  const [hover, setHover] = useState<string | null>(null);
  const base = d.base_points ?? 0;
  const active = d.features.filter((f) => !f.missing && (f.points ?? 0) > 0).sort((a, b) => (b.points ?? 0) - (a.points ?? 0));
  const zero = d.features.filter((f) => !f.missing && !(f.points ?? 0));
  const missing = d.features.filter((f) => f.missing);
  const final = d.partial_score ?? d.score ?? 0;
  // points cumulés : chaque barre démarre où la précédente s'arrête
  const rows = active.map((f, k) => {
    const from = base + active.slice(0, k).reduce((a, x) => a + (x.points ?? 0), 0);
    return { f, from, to: from + (f.points ?? 0) };
  });
  return (
    <div>
      <Row hover={hover} setHover={setHover} id="base" label="Base rate (no signal)" sub={`σ(β₀ = ${d.bias}) — the score of a site with no risk signal`} from={0} to={base}
        color="var(--line-strong)" right={base.toFixed(1)} />
      {rows.map(({ f, from, to }) => (
        <Row hover={hover} setHover={setHover} key={f.key} id={f.key} label={SHORT[f.key] ?? f.label} sub={`${evidenceLine(f)} · weight ${f.weight} × x=${f.value}`} from={from} to={to}
          color="var(--text)" right={`+${(f.points ?? 0).toFixed(1)}`} />
      ))}
      <div className="my-1 border-t border-line" />
      <Row hover={hover} setHover={setHover} id="final" label={d.abstain ? "Partial score (abstains)" : "Provenance risk"} from={0} to={final}
        sub={d.abstain ? "Not enough measured features to score: shown for reference only." : `logit ${d.logit} → ${final} / 100`}
        color={d.abstain ? "var(--faint)" : bandColor(d.band)} dashed={d.abstain} right={final.toFixed(1)} />
      {(zero.length > 0 || missing.length > 0) && (
        <div className="mt-3 grid gap-3 text-[12.5px] md:grid-cols-2">
          {zero.length > 0 && (
            <div>
              <div className="mb-1 text-faint">Checked, no risk found (+0)</div>
              <ul className="space-y-0.5">{zero.map((f) => <li key={f.key} title={evidenceLine(f)} className="truncate text-muted">○ {f.label}</li>)}</ul>
            </div>
          )}
          {missing.length > 0 && (
            <div>
              <div className="mb-1 text-faint">Not measured ({missing.length}; abstains above 3)</div>
              <ul className="space-y-0.5">{missing.map((f) => <li key={f.key} title={f.why_missing} className="truncate text-faint">– {f.label}: <span className="italic">{f.why_missing}</span></li>)}</ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Row({ id, label, sub, from, to, color, dashed, right, hover, setHover }: {
  hover: string | null; setHover: (v: string | null) => void;
    id: string; label: string; sub?: string; from: number; to: number; color: string; dashed?: boolean; right: string;
}) {
  return (
    <div className="grid grid-cols-[minmax(150px,240px)_1fr_64px] items-center gap-3 py-1"
      onMouseEnter={() => setHover(id)} onMouseLeave={() => setHover(null)}>
      <div className="truncate text-[13px]" title={label}>{label}</div>
      <div className="relative h-5">
        {[40, 70].map((x) => <div key={x} className="absolute top-0 h-full w-px bg-line" style={{ left: `${x}%` }} />)}
        <div className="absolute top-0.5 h-4 rounded-[2px]"
          style={{ left: `${Math.min(from, to)}%`, width: `${Math.max(0.6, Math.abs(to - from))}%`, background: dashed ? "transparent" : color,
            border: dashed ? `1px dashed ${color}` : undefined }} />
        {hover === id && sub && (
          <div className="pointer-events-none absolute left-0 top-full z-20 mt-1 max-w-[560px] rounded-md border border-line-strong bg-panel p-2 text-[12px] text-text shadow-[0_6px_20px_rgba(20,30,50,.12)]">
            {sub}
          </div>
        )}
      </div>
      <div className="num text-right text-[12.5px] text-muted">{right}</div>
    </div>
  );
}
