# Propaganda Observer

Live, cross-platform detection of coordinated propaganda, bot-driven amplification and bad-actor behaviour, with source provenance scoring. Built for the **Junction × Hostinger** hackathon.

Describe an event or a claim. A planning agent turns it into search terms in every relevant language. Observer then:

1. collects public posts live from the web, YouTube, Bluesky, TikTok, Instagram and Telegram;
2. groups what says the same thing into narratives;
3. explains, with evidence, what looks coordinated, automated or pushed by documented influence networks.

## Live

**https://srv2160677.hstgr.cloud** (Hostinger VPS, HTTPS)

| Access | How | What you can do |
|---|---|---|
| **Public demo** | Open the link, no account needed | Explore the published French case, read-only. No external or paid call is ever made |
| **Judges / admins** | "Admin sign in", with the credentials given by the team | Everything: plan a new observation, collect live, run AI investigations, publish the demo |

**Real case shipped in the public demo:** the French autumn 2026 protests. Observer finds:

- Pravda-network relays posting the same text within seconds;
- a Telegram channel family acting in sync, including one channel that is on no list;
- Telegram posts taken up by Pravda sites within minutes (median 13 min, every hop proven by a citation of the source channel), while articles reach Bluesky after hours (median 8.7 h): relay speed versus organic sharing;
- undeclared automated accounts;
- the themes pushed by networks versus organic mobilisation.

These findings match what Alliance4Europe and VIGINUM published about the same events. See [`docs/cas-france-automne-2026.md`](docs/cas-france-automne-2026.md).

## What it does

| Screen | What you see |
|---|---|
| **Brief** | Activity over time with detected peaks. The default "Alerts" view colours what needs a look in red tones (priority and review narratives, suspected accounts, false claims) and the rest in grey. Narratives to review, top amplifiers |
| **Narratives** | Each narrative with its verdict (Organic / Review / Priority), the signals behind it with their weights, spread over time, publications. An **AI investigation** lets an investigator and a skeptic debate, then a judge decides; every claim cites the evidence |
| **Network** | Accounts ↔ narratives; bridges between narratives |
| **Coordination** | Groups of accounts that performed the **same action** (same own text, same link, same hashtag combination) within a coordination window **learnt from the data**, CooRnet-style. Each group has a timeline barcode |
| **Diffusion** | How content moves between platforms, and how fast: every cross-platform hop placed by its delay, from minutes (organised relay) to days (organic sharing). Hops are **proven** (the post cites or links its source) or **inferred** (closest earlier text), and shown as such. There is no "patient zero": we only see part of the web |
| **Themes** | Every post clustered into themes across languages: who pushes which theme (listed networks, automated accounts, news sites, other accounts), in which language, over time |
| **Accounts** | Every account, with risk flags and a ranked list of suspected coordinated or automated accounts, with evidence |
| **Trust card** | Provenance score of a domain or account with raw evidence. Also an API: `GET /v1/provenance?target=` |
| **Reliability** | Precision, recall and false-positive rate of every detector on labelled data it never saw while tuning, with confidence intervals and an error gallery |

## Detection quality, measured

`uv run python -m eval.run` writes `data/eval/results.json`, which the Reliability page displays.

| Detector | Precision | Recall | False-positive rate |
|---|---|---|---|
| Accounts (Cresci-2017 sample) | 94.7 % | 35.4 % | 2.0 % |
| Listed domains (Pravda, Iffy vs. Lin et al. trusted) | 100 % | 98 % on the Pravda list | 0 / 1,260 trusted domains |
| Coordination, narrative level (injected swarms vs. legitimate virality) | 100 % | 78 % | 0 % |
| Coordinated accounts, account level (same bench, all scenarios mixed with real posts) | 99.6 % | 46 % | 0.47 % |

How to read these numbers, and the known limits (also shown in the app):

- the domain recall on the Pravda list mostly measures a lookup in a list that contains those domains; on a list our registry does not hold (Iffy), recall falls to 0.8 %. The meaningful figure there is the false-positive rate on trusted domains;
- the coordination benches are synthetic and were built by us (thresholds were frozen before): their 100 % precision is an upper bound, and with 0 errors out of 90 cases the 95 % interval still reaches about 4 %;
- account data is Twitter 2014 to 2016 (Cresci-2017): no labelled dataset exists for Bluesky, Telegram or TikTok accounts;
- a "patient swarm" that spreads over 2 days is not detected;
- posting volume alone is weak evidence (on Cresci-2017, ≥ 72 posts/day flags 3.7 % of genuine users);
- X/Twitter is not collected (paid API).

## Architecture

```
browser ──► Next.js 16 (UI + /backend proxy + Better Auth) ──(internal token + role)──► FastAPI (Python 3.12)
                                                                                         ├─ collectors · detectors · agents
                                                                                         ├─ Postgres + pgvector
                                                                                         └─ Redis (bus, caches)
```

- **Agents** run through the **Hostinger AI Router** (Claude, embeddings, Whisper). A hard budget cap is enforced in code.
- **Privacy**: authors are pseudonymised at ingestion: salted hash, then HMAC with a secret key (`PSEUDO_KEY`, never committed), so a public salt is not enough to re-identify anyone. Individual accounts are shown as `platform·hash`.
- **Access**:
  - administrators sign in and get full access: live collection, AI investigations, publishing;
  - the **public demo needs no account** and serves only a published snapshot, with no external or paid call. This is enforced server-side, with a guard that blocks any AI call.

  See [`docs/acces-et-demo.md`](docs/acces-et-demo.md).

## Deployment (Hostinger)

Hostinger VPS (KVM 2) with Docker and the preinstalled Traefik, which terminates HTTPS with Let's Encrypt.

- Only the Next.js service is exposed. The API, Postgres and Redis stay on the internal Docker network: their ports are closed to the Internet.
- Secrets live only on the server (mode 600), never in git.
- Update in one command: `infra/deploy.sh`.

Files: `infra/docker-compose.prod.yml`, `infra/Dockerfile.api`, `web/Dockerfile`. Full procedure: [`docs/deploiement.md`](docs/deploiement.md).

## Run locally

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 24 with pnpm, Docker.

```bash
# 1. Databases (Postgres + pgvector on :5442, Redis on :6380)
docker compose -p propaganda-observer -f infra/docker-compose.dev.yml up -d

# 2. API
cp .env.example .env            # fill in the keys; set API_TOKEN, PSEUDO_SALT and PSEUDO_KEY to long random values
uv sync
uv run uvicorn observer.api.main:app --port 8010

# 3. Web
cd web
pnpm install
# web/.env.local:
#   BACKEND_URL=http://localhost:8010   BACKEND_TOKEN=<same as API_TOKEN>
#   BETTER_AUTH_SECRET=<random>   BETTER_AUTH_URL=http://localhost:3000
#   AUTH_DATABASE_URL=postgresql://…   ADMIN_EMAIL=…   ADMIN_PASSWORD=…
node --env-file=.env.local scripts/setup-auth.mjs   # creates the auth tables and the admin account
pnpm dev                                            # http://localhost:3000
```

Tests: `uv run pytest -q`. Front-end checks: `cd web && pnpm exec tsc --noEmit && pnpm lint`.

## Repository map

| Path | Content |
|---|---|
| `observer/collectors/` | Google News, YouTube, Bluesky, TikTok and Instagram (Apify), Telegram public previews, reference-network RSS |
| `observer/tools/` | Copy-paste (MinHash LSH), semantic clusters, link shares, bursts, narratives and verdicts, suspected accounts, coordination network, cross-platform diffusion, themes, provenance, media (transcripts, OCR, frame hashes) |
| `observer/agents/` | Planner, stance, investigation (investigator ⇄ skeptic → judge) |
| `observer/api/` | REST + SSE, views, publication of the demo snapshot |
| `observer/scripts/` | One-off maintenance (pseudonym re-keying migration) |
| `eval/` | Labelled benchmarks and metrics |
| `web/` | Next.js app (UI, `/backend` proxy, Better Auth) |
| `infra/` | Docker Compose (dev and production), API Dockerfile, deploy script |
| `data/registry/` | Documented networks, listed sources, major media (extendable, no code) |
| `docs/` | Demo script, real case report, access model, deployment, feasibility spikes |
| `SPECS.md`, `UI.md`, `BACKLOG.md` | Specifications (in French) |
