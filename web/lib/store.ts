"use client";
import { create } from "zustand";
import type { Severity, Stance } from "./views";

export type Tab = "brief" | "stories" | "network" | "coordination" | "diffusion" | "themes" | "accounts";

export interface Step { key: string; label: string; state: "pending" | "running" | "done" | "skipped" | "error"; count?: number | null; detail?: string; at?: string }
export interface Progress { pass: { state?: "running" | "idle"; at?: string; next_at?: string; new?: number }; steps: Step[] }

interface Filters { platforms: string[]; stances: Stance[]; severities: Severity[] }

interface OpsState {
  tab: Tab;
  setTab: (t: Tab) => void;
  version: number;          // incrémenté à chaque nouvelle donnée live : les vues se rechargent
  bump: () => void;
  connected: boolean;
  setConnected: (c: boolean) => void;
  status: string;
  setStatus: (s: string) => void;
  progress: Progress | null;
  setProgress: (p: Progress) => void;
  filters: Filters;
  toggle: <K extends keyof Filters>(k: K, v: Filters[K][number]) => void;
  clearFilters: () => void;
  story: string | null;
  openStory: (id: string | null) => void;
  account: string | null;
  openAccount: (id: string | null) => void;
}

export const useOps = create<OpsState>((set) => ({
  tab: "brief",
  setTab: (tab) => set({ tab }),
  version: 0,
  bump: () => set((s) => ({ version: s.version + 1 })),
  connected: false,
  setConnected: (connected) => set({ connected }),
  status: "",
  setStatus: (status) => set({ status }),
  progress: null,
  setProgress: (progress) => set({ progress }),
  filters: { platforms: [], stances: [], severities: [] },
  toggle: (k, v) => set((s) => {
    const cur = s.filters[k] as string[];
    const next = cur.includes(v as string) ? cur.filter((x) => x !== v) : [...cur, v as string];
    return { filters: { ...s.filters, [k]: next } };
  }),
  clearFilters: () => set({ filters: { platforms: [], stances: [], severities: [] } }),
  story: null,
  openStory: (story) => set({ story, tab: "stories" }),
  account: null,
  openAccount: (account) => set({ account }),
}));

/** Filtre générique appliqué par tous les écrans. Vide = tout passe. */
export function passes(f: Filters, o: { platforms?: string[]; platform?: string; stance?: Stance; level?: Severity }) {
  const plats = o.platforms ?? (o.platform ? [o.platform] : []);
  if (f.platforms.length && !plats.some((p) => f.platforms.includes(p))) return false;
  if (f.stances.length && o.stance && !f.stances.includes(o.stance)) return false;
  if (f.severities.length && o.level && !f.severities.includes(o.level)) return false;
  return true;
}
