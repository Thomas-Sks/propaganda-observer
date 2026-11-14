"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Empty, Section } from "@/components/ui/kit";
import UserMenu from "@/components/ui/UserMenu";
import { isAdmin, useSession } from "@/lib/auth-client";

interface EventRow { slug: string; label: string; status: string; created_at: string }
interface PlanResult {
  slug: string;
  config: { label: string; description?: string; keywords: string[]; keyword_langs?: Record<string, string>; hashtags: string[]; start: string; end: string; country: string; languages: string[] };
  volumes: Record<string, number>;
}

const EXAMPLES = [
  "Pro-Russian claims that Ukraine's Azov brigade runs secret 'torture chambers' near Kyiv (November 2026)",
  "Storm-1516 fake Washington Examiner article: McKinsey would fund Édouard Philippe's 2027 campaign",
  "Matryoshka fake media videos targeting Spain's 29 November 2026 election (leave the EU, Ukraine aid ruins Europe)",
  "Claims on social media that 2026 heat records were faked by national weather agencies",
  "Coordinated accounts pushing narratives about Taiwan's defence budget on YouTube and TikTok",
];

export default function Launch() {
  const router = useRouter();
  const [desc, setDesc] = useState("");
  const [phase, setPhase] = useState<"idle" | "planning" | "review" | "starting">("idle");
  const [plan, setPlan] = useState<PlanResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [events, setEvents] = useState<EventRow[]>([]);
  const planRef = useRef<HTMLDivElement>(null);
  const session = useSession();
  const admin = isAdmin(session.data?.user);
  // Dès que le plan (ou l'état « en cours ») apparaît, on y amène l'utilisateur au lieu de le laisser chercher
  useEffect(() => {
    if (phase === "planning" || phase === "review") planRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [phase]);

  useEffect(() => { api<EventRow[]>("/api/events").then(setEvents).catch(() => {}); }, []);

  async function submit(text: string) {
    if (!text.trim()) return;
    setDesc(text); setError(null); setPhase("planning");
    try {
      setPlan(await api<PlanResult>("/api/events/plan", { method: "POST", body: JSON.stringify({ description: text }) }));
      setPhase("review");
    } catch (err) { setError(String(err)); setPhase("idle"); }
  }

  async function start() {
    if (!plan) return;
    setPhase("starting");
    await api(`/api/events/${plan.slug}/start`, { method: "POST" });
    router.push(`/ops/${plan.slug}`);
  }

  const byLang = plan ? Object.entries(plan.volumes).reduce<Record<string, [string, number][]>>((acc, [k, v]) => {
    const l = (plan.config.keyword_langs?.[k] ?? "—").toUpperCase();
    (acc[l] ??= []).push([k, v]);
    return acc;
  }, {}) : {};
  const maxVol = Math.max(1, ...Object.values(plan?.volumes ?? { a: 1 }));

  return (
    <div className="min-h-screen bg-bg">
      <header className="flex h-14 items-center gap-6 bg-navy px-5 text-white">
        <span className="text-[15px] font-bold tracking-[0.08em]">OBSERVER</span>
        <nav className="flex gap-5 text-[14px] text-white/75">
          <Link href="/" className="font-semibold text-white">Observations</Link>
          <Link href="/trust" className="hover:text-white">Trust card</Link>
          <Link href="/reliability" className="hover:text-white">Reliability</Link>
        </nav>
        <span className="ml-auto"><UserMenu /></span>
      </header>

      <main className="mx-auto max-w-[960px] space-y-8 px-5 py-12">
        <div>
          <h1 className="text-[28px] font-semibold leading-tight">Watch a narrative as it spreads.</h1>
          <p className="mt-2 max-w-[720px] text-[15px] text-muted">
            Describe an event or a claim. An agent turns it into search terms in every relevant language, then Observer
            collects live from the web, Bluesky, YouTube, TikTok, Instagram and Telegram, groups what says the same thing,
            and explains — with evidence — what looks coordinated.
          </p>
        </div>

        {!session.isPending && !admin && (
          <div className="rounded-md border border-accent/40 bg-[#eef3fd] p-4 text-[14px]">
            <b>Public demo (read-only, no account needed).</b> Open the observation below to explore a real case: the
            French autumn 2026 protests, with coordinated networks, automated accounts and themes. These are published
            results; starting new observations and running new AI investigations is reserved to administrators.
          </div>
        )}
        {admin && <form onSubmit={(e) => { e.preventDefault(); submit(desc); }} className="rounded-md border border-line bg-panel p-4">
          <label className="text-[13px] font-semibold">New observation</label>
          <div className="mt-2 flex gap-2">
            <input value={desc} onChange={(e) => setDesc(e.target.value)} disabled={phase === "planning"}
              placeholder="e.g. claims about secret torture chambers near Kyiv, November 2026"
              className="h-11 flex-1 rounded-md border border-line-strong bg-panel px-3 text-[15px] outline-none focus:border-accent" />
            <button disabled={phase === "planning"} className="rounded-md bg-accent px-5 text-[14px] font-medium text-white disabled:opacity-60">
              {phase === "planning" ? "Planning…" : "Plan"}
            </button>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {EXAMPLES.map((x) => (
              <button type="button" key={x} onClick={() => submit(x)} disabled={phase === "planning"}
                className="rounded-full border border-line-strong px-3 py-1 text-left text-[12.5px] text-muted hover:border-accent hover:text-accent">{x}</button>
            ))}
          </div>
          {error && <div className="mt-3 text-[13px] text-sev-priority">{error}</div>}
        </form>}

        <div ref={planRef} className="scroll-mt-4" />
        {phase === "planning" && (
          <section className="rounded-md border border-accent bg-panel p-5">
            <div className="flex items-center gap-3">
              <span className="inline-block h-5 w-5 animate-spin rounded-full border-[3px] border-accent border-t-transparent" />
              <span className="text-[15px] font-semibold">Planning “{desc.slice(0, 80)}{desc.length > 80 ? "…" : ""}”</span>
            </div>
            <ol className="mt-3 space-y-1.5 text-[13.5px] text-muted">
              <li className="row-in">1. An agent expands the description into search terms in every relevant language…</li>
              <li className="row-in" style={{ animationDelay: "2s" }}>2. It sets the time window and the narrative to watch…</li>
              <li className="row-in" style={{ animationDelay: "4s" }}>3. Each term is checked against real news volume in that window (≈ 20–40 s)…</li>
            </ol>
          </section>
        )}

        {plan && phase !== "planning" && (
          <section className="rounded-md border border-line bg-panel">
            <div className="flex items-start gap-4 border-b border-line p-4">
              <div className="flex-1">
                <div className="text-[17px] font-semibold">{plan.config.label}</div>
                <div className="num mt-0.5 text-[12.5px] text-muted">{plan.config.start} → {plan.config.end} · {plan.config.languages.join(", ").toUpperCase()}</div>
                {plan.config.description && <p className="mt-2 text-[14px] leading-relaxed">{plan.config.description}</p>}
              </div>
              <button onClick={start} disabled={phase === "starting"} className="flex items-center gap-2 rounded-md bg-accent px-4 py-2 text-[14px] font-medium text-white disabled:opacity-60">
                {phase === "starting" && <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" />}
                {phase === "starting" ? "Starting…" : "Start monitoring →"}
              </button>
            </div>
            <div className="grid gap-4 p-4 md:grid-cols-2">
              {Object.entries(byLang).map(([lang, rows]) => (
                <div key={lang}>
                  <div className="text-[12.5px] font-semibold text-muted">{lang} · search terms and live volume in the window</div>
                  <ul className="mt-1">
                    {rows.sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                      <li key={k} className={`flex items-center gap-3 border-b border-line py-1.5 text-[13.5px] ${v > 0 ? "" : "text-faint line-through"}`}>
                        <span className="flex-1 truncate">{k}</span>
                        <span className="block h-1.5 rounded-full bg-muted" style={{ width: `${(Math.max(0, v) / maxVol) * 90}px` }} />
                        <span className="num w-8 text-right text-[12px] text-muted">{v}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
            <div className="border-t border-line px-4 py-3 text-[13px] text-muted">Hashtags: <span className="text-text">{plan.config.hashtags.map((h) => `#${h}`).join("  ")}</span></div>
          </section>
        )}

        <Section title="Observations" hint="click to open the operations room">
          {events.length ? (
            <ul className="divide-y divide-line rounded-md border border-line bg-panel">
              {events.map((e) => (
                <li key={e.slug}>
                  <button onClick={() => router.push(`/ops/${e.slug}`)} className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-panel-2">
                    <span className={`h-2 w-2 rounded-full ${e.status === "live" ? "live-dot bg-accent" : "bg-line-strong"}`} />
                    <span className="flex-1 text-[14px]">{e.label}</span>
                    <span className="num text-[12px] text-muted">{e.status} · {e.created_at.slice(0, 10)}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : <Empty text="No observation yet." />}
        </Section>
      </main>
    </div>
  );
}
