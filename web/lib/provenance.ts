import { API } from "./api";

/* Score de provenance (SPECS §3bis) — GET /v1/provenance?target=…
   NEXT_PUBLIC_PROVENANCE_API_URL permet de viser un autre serveur (ex. :8022 pendant une vérification). */
export const PROVENANCE_API = API;

export type Band = "priority" | "review" | "organic" | "insufficient_data";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Ev = Record<string, any> | null;

export interface ProvFeature {
  key: string;
  label: string;
  weight: number;
  value: number | null;
  contribution: number | null;
  points: number | null;
  missing: boolean;
  evidence: Ev;
  why_missing?: string;
}

export interface Provenance {
  target: string;
  kind: "domain" | "account";
  subject?: string;
  registrable?: string;
  platform?: string;
  error?: string;
  score: number | null;
  partial_score?: number;
  band: Band;
  abstain: boolean;
  missing?: string[];
  logit?: number;
  base_points?: number;
  bias?: number;
  features: ProvFeature[];
  model_version: string;
  lists_frozen: string;
  computed_at: string;
  disclaimer: string;
  limits: string[];
  signals?: Ev;
  method: {
    model: string; formula: string; bias: number; abstention: string; calibration: string;
    weights: Record<string, { weight: number; label: string }>; bands: Record<string, string>;
  };
}

export async function getProvenance(target: string, signal?: AbortSignal): Promise<Provenance> {
  const r = await fetch(`${PROVENANCE_API}/v1/provenance?target=${encodeURIComponent(target)}`, { signal });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}
