"use client";
import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { signIn } from "@/lib/auth-client";

export default function LoginPage() {
  return <Suspense fallback={<div className="min-h-screen bg-bg" />}><Login /></Suspense>;
}

function Login() {
  const router = useRouter();
  const next = useSearchParams().get("next") || "/";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(null);
    const { error } = await signIn.email({ email, password });
    setBusy(false);
    if (error) { setErr(error.status === 429 ? "Too many attempts, wait a minute." : "Wrong email or password."); return; }
    router.push(next.startsWith("/") ? next : "/");
    router.refresh();
  }
  return (
    <div className="flex min-h-screen flex-col bg-bg">
      <header className="flex h-14 items-center bg-navy px-5 text-white"><span className="text-[15px] font-bold tracking-[0.08em]">OBSERVER</span></header>
      <main className="flex flex-1 items-center justify-center p-5">
        <form onSubmit={submit} className="w-full max-w-[400px] rounded-md border border-line bg-panel p-6 shadow-sm">
          <h1 className="text-[20px] font-semibold">Administrator sign in</h1>
          <p className="mt-1 text-[13.5px] text-muted">Live collection, new observations and AI investigations. Accounts are provided by the organisers.</p>
          <label className="mt-5 block text-[13px] font-semibold" htmlFor="email">Email</label>
          <input id="email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)}
            className="mt-1 h-10 w-full rounded-md border border-line-strong bg-panel px-3 text-[14px] outline-none focus:border-accent" />
          <label className="mt-3 block text-[13px] font-semibold" htmlFor="password">Password</label>
          <input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)}
            className="mt-1 h-10 w-full rounded-md border border-line-strong bg-panel px-3 text-[14px] outline-none focus:border-accent" />
          {err && <div className="mt-3 text-[13px] text-sev-priority">{err}</div>}
          <button disabled={busy} className="mt-5 flex h-10 w-full items-center justify-center gap-2 rounded-md bg-accent text-[14px] font-medium text-white disabled:opacity-60">
            {busy && <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" />}
            {busy ? "Signing in…" : "Sign in"}
          </button>
          <div className="my-5 flex items-center gap-3 text-[12px] text-faint"><span className="h-px flex-1 bg-line" />or<span className="h-px flex-1 bg-line" /></div>
          <Link href="/" className="flex h-10 w-full items-center justify-center rounded-md border border-accent text-[14px] font-medium text-accent hover:bg-[#eef3fd]">
            Explore the public demo →
          </Link>
          <p className="mt-2 text-center text-[12px] text-muted">No account needed: the French autumn 2026 case, read-only.</p>
        </form>
      </main>
    </div>
  );
}
