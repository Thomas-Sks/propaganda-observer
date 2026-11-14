"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { isAdmin, signOut, useSession } from "@/lib/auth-client";

/** Compte connecté (dans l'en-tête bleu marine) : rôle visible, déconnexion. */
export default function UserMenu() {
  const { data } = useSession();
  const router = useRouter();
  if (!data) {
    return (
      <span className="flex items-center gap-2 text-[12.5px]">
        <span className="rounded bg-white/15 px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-white"
          title="Public demo: published data only, no live collection and no AI call">public demo</span>
        <Link href="/login" className="rounded-md border border-white/25 px-2 py-1 text-white/85 hover:bg-white/10">Admin sign in</Link>
      </span>
    );
  }
  const admin = isAdmin(data.user);
  return (
    <span className="flex items-center gap-2 text-[12.5px]">
      <span className={`rounded px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${admin ? "bg-accent text-white" : "bg-white/15 text-white"}`}
        title={admin ? "Full access: new observations, live collection, AI investigations" : "Read-only: published data only"}>
        {admin ? "admin" : "read-only"}
      </span>
      <span className="hidden text-white/75 md:inline">{data.user.email}</span>
      <button onClick={async () => { await signOut(); router.push("/"); router.refresh(); }}
        className="rounded-md border border-white/25 px-2 py-1 text-white/85 hover:bg-white/10">Sign out</button>
    </span>
  );
}
