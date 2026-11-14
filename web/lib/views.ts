import { api } from "./api";

export type Severity = "priority" | "review" | "organic" | "insufficient_data";
export type Stance = "promotes" | "debunks" | "neutral" | "unclassified";
export type Risk = "high" | "medium" | "none";

export interface Flag { key: string; label: string; detail: string; risk: "high" | "medium" | "low" }
export interface Account {
  id: string; label: string; platform: string; items: number; stories: string[];
  stance_mix: Partial<Record<Stance, number>>; followers: number | null; created_at: string | null;
  flags: Flag[]; risk: Risk; first_ts: string; last_ts: string; community?: number; degree?: number;
}
export interface StoryCard {
  id: string; title: string; level: Severity; score: number; stance: Stance; platforms: string[];
  items: number; accounts: number; first_ts: string; last_ts: string;
  headline_signal: string | null; stance_quote: string | null; days: [string, number][];
}
export interface Signal { name: string; value: number | string; weight: number; explanation: string }
export interface Publication {
  uid: string; platform: string; format: string; ts: string; url: string | null; text: string; account: string;
  account_id: string; similarity: number | null; links: string[];
  transcript?: string | null; ocr?: string | null; caption?: string;
}
export interface StoryDetail extends StoryCard {
  signals: Signal[]; publications: Publication[]; accounts_detail: Account[];
}
export interface Summary {
  event: { slug: string; label: string; description?: string; sources: string[]; start?: string; end?: string; keywords: string[]; languages: string[] };
  kpis: { items: number; accounts: number; platforms: number; stories: number; priority: number; review: number; promotes: number; debunks: number };
  daily: ({ day: string } & Partial<Record<Stance, number>>)[];
  peaks: { period: string; count: number; z: number; baseline: number; explanation: string }[];
  platform_daily: Record<string, [string, number][]>;
  stories: StoryCard[];
  top_accounts: Account[];
}
export interface NetEdge { source: string; target: string; weight: number; stories: string[]; stance: Stance }
export interface Network {
  nodes: Account[]; edges: NetEdge[];
  communities: { id: number; size: number; name: string; members: string[] }[];
  stories: Record<string, { title: string; stance: Stance; level: Severity }>;
}
export interface AccountDetail extends Account {
  story_info: Record<string, { title: string; stance: Stance; level: Severity }>;
  publications: { uid: string; ts: string; url: string | null; text: string; stance: Stance; format: string }[];
}

export const getSummary = (s: string) => api<Summary>(`/api/events/${s}/summary`);
export const getStory = (s: string, id: string) => api<StoryDetail>(`/api/events/${s}/stories/${id}`);
export const getNetwork = (s: string) => api<Network>(`/api/events/${s}/network`);
export const getAccounts = (s: string) => api<Account[]>(`/api/events/${s}/accounts`);
export interface Suspect extends Omit<Account, "risk"> {
  score: number; level: "likely" | "review"; repeats: number; flagged_stories: string[];
  declared_bot: boolean; posts_per_day: number | null; family: { id: string; label: string }[];
  evidence: { key: string; weight: number; text: string }[];
  partners: { id: string; label: string; stories: string[] }[];
}
export interface Suspects { accounts: Suspect[]; window_min: number; thresholds: { likely: number; review: number } }
export const getSuspects = (s: string) => api<Suspects>(`/api/events/${s}/suspects`);
export interface CoordNode {
  id: string; label: string; platform: string; listed: string | null; automated: boolean;
  suspect_level: "likely" | "review" | null; suspect_score: number | null;
  posts: number; coordinated_posts: number; degree: number; strength: number; community: number | null;
}
export interface CoordExample { kind: string; key: string; text: string; a_ts: string; b_ts: string; delay_s: number }
export interface CoordEdge { source: string; target: string; weight: number; strong: boolean; kind: string; kinds: Record<string, number>; examples: CoordExample[] }
export interface CoordCommunity {
  id: number; name: string; why: string; size: number; members: string[]; edges: number; strong_edges: number;
  kinds: Record<string, number>; platforms: Record<string, number>; listed: number; automated: number;
  first_ts: string | null; last_ts: string | null;
  shared: { kind: string; value: string; pairs: number; accounts: number }[];
}
export interface Coordination {
  window_s: number; n_delays: number; actions: number; action_kinds: Record<string, number>;
  nodes: CoordNode[]; edges: CoordEdge[]; communities: CoordCommunity[];
  barcode: Record<string, { ts: string; c: boolean }[]>; method: string[];
}
export const getCoordination = (s: string) => api<Coordination>(`/api/events/${s}/coordination`);
export interface Theme {
  id: number; name: string; framing: string; keywords: string[]; items: number; accounts: number;
  platforms: Record<string, number>; langs: Record<string, number>; sources: Record<string, number>;
  stance: Record<string, number>; series: number[]; narratives: string[];
  top_accounts: { id: string; label: string; posts: number; source: string }[];
  examples: { uid: string; platform: string; url: string | null; ts: string; text: string }[];
}
export interface Themes { themes: Theme[]; days: string[]; k: number; n_items: number; method: string[] }
export const getThemes = (s: string) => api<Themes>(`/api/events/${s}/themes`);
export const getAccount = (s: string, id: string) => api<AccountDetail>(`/api/events/${s}/accounts/${id}`);

export const SEVERITY: Record<string, { label: string; color: string; help: string }> = {
  priority: { label: "Priority", color: "var(--sev-priority)", help: "Strong, independent coordination signals." },
  review: { label: "Review", color: "var(--sev-review)", help: "Some coordination signals — worth a human look." },
  organic: { label: "Organic", color: "var(--sev-organic)", help: "No coordination signal above threshold." },
  insufficient_data: { label: "No data", color: "var(--faint)", help: "Not enough data to judge." },
};
export const STANCE: Record<Stance, { label: string; short: string; icon: string; color: string; help: string }> = {
  promotes: { label: "Repeats the false claim", short: "Repeats claim", icon: "▲", color: "var(--st-promotes)", help: "Repeats the documented false claim as true." },
  debunks: { label: "Debunks the claim", short: "Debunks claim", icon: "✓", color: "var(--st-debunks)", help: "Fact-check, refutation, or frames it as propaganda." },
  neutral: { label: "Neutral report", short: "Neutral", icon: "●", color: "var(--st-neutral)", help: "Reports facts without endorsing the claim." },
  unclassified: { label: "Not in a narrative", short: "Other", icon: "·", color: "var(--st-unclassified)", help: "Item not grouped into a narrative yet." },
};
export const PLATFORM: Record<string, string> = {
  web: "WEB", bluesky: "BSKY", youtube: "YT", tiktok: "TT", instagram: "IG", telegram: "TG", x: "X", mastodon: "MAST", facebook: "FB",
};
export const PLATFORM_NAME: Record<string, string> = {
  web: "Web", bluesky: "Bluesky", youtube: "YouTube", tiktok: "TikTok", instagram: "Instagram", telegram: "Telegram", x: "X", mastodon: "Mastodon", facebook: "Facebook",
};
export const fmtDay = (d: string) => new Date(d + "T00:00:00Z").toLocaleDateString("en-GB", { day: "2-digit", month: "short", timeZone: "UTC" });
export const fmtTs = (ts: string) => new Date(ts).toISOString().slice(5, 16).replace("T", " ") + "Z";
