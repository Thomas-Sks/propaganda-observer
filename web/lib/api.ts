/** Tous les appels passent par le backend-for-frontend Next (/backend), qui vérifie la session et le rôle. */
export const API = "/backend";

export type Platform = "x" | "youtube" | "tiktok" | "instagram" | "facebook" | "bluesky" | "mastodon" | "telegram" | "web";

export interface ContentItem {
  platform: Platform;
  post_id: string;
  url: string | null;
  ts: string;
  author_pseudo: string;
  text: string;
  urls_canon: string[];
  hashtags: string[];
  lang: string | null;
  event: string | null;
  account?: { created_at: string | null; followers: number | null; posts_count: number | null };
  metrics?: Record<string, number>;
}

export interface GraphNode {
  id: string;
  type: "source" | "cluster";
  label: string;
  platform?: Platform;
  count: number;
  kind?: string;
  authors?: number;
  platforms?: Platform[];
  level?: "organic" | "review" | "priority" | "insufficient_data";
  item_uids?: string[];
  kinds?: string[];
  score?: number;
  signals?: Signal[];
  first_ts?: string;
  last_ts?: string;
  clustered?: boolean;
}
export interface Signal { name: string; value: number | string; weight: number; explanation: string }
export interface GraphEdge { source: string; target: string; kind: string }
export interface GraphPayload { nodes: GraphNode[]; edges: GraphEdge[] }

export interface Stats { items: number; off_topic?: number; clusters: number; platforms: Platform[]; sources: number; at: string }

export interface PlanResult {
  slug: string;
  config: { label: string; keywords: string[]; hashtags: string[]; start: string; end: string; country: string; lookalike_media: string[]; rationale: string };
  volumes: Record<string, number>;
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${API}${path}`, { ...init, headers: { "Content-Type": "application/json", ...init?.headers } });
  // Session admin expirée : rechargement complet vers la connexion (api() n'est pas un composant, pas de routeur ici)
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination
  if (r.status === 401 && typeof window !== "undefined") { window.location.href = `/login?next=${encodeURIComponent(location.pathname)}`; }
  if (!r.ok) {
    const body = await r.text();
    let msg = body;
    try { msg = JSON.parse(body).detail ?? body; } catch {}
    throw new Error(String(msg));
  }
  return r.json() as Promise<T>;
}

export const platformColor = (p?: string) => `var(--p-${p ?? "web"})`;
export const platformLabel: Record<string, string> = {
  x: "X", youtube: "YouTube", tiktok: "TikTok", instagram: "Instagram", facebook: "Facebook",
  bluesky: "Bluesky", mastodon: "Mastodon", telegram: "Telegram", web: "Web",
};

export const levelMeta: Record<string, { label: string; color: string; help: string }> = {
  organic: { label: "Organic", color: "var(--organic)", help: "Normal coverage. No coordination signal above threshold." },
  review: { label: "Review", color: "var(--review)", help: "Some coordination signals. Worth a human look." },
  priority: { label: "Priority", color: "var(--critical)", help: "Strong, independent coordination signals." },
  insufficient_data: { label: "Insufficient data", color: "var(--faint)", help: "Not enough data to judge." },
};

export const ago = (ts: string) => {
  const m = Math.round((Date.now() - +new Date(ts)) / 60000);
  return m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} d ago`;
};
