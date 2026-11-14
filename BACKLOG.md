# Backlog : Propaganda Observer

> Équipe : l'utilisateur + Claude. Construction en **tranches verticales** : chaque tranche marche de bout en bout et elle est déployée sur le VPS avant de passer à la suivante.
> Priorités : **P0** = la démo ne tient pas sans · **P1** = gain net de score · **P2** = bonus.
> Référence : [`SPECS.md`](SPECS.md), [`UI.md`](UI.md).

Légende : `[ ]` à faire · `[~]` en cours · `[x]` fait · ✅ critère d'acceptation

---

## S0 : Socle et accès (P0)

- [ ] Dépôt git + arborescence `api/ workers/ tools/ agents/ web/ infra/ eval/ data/`
- [ ] `.env.example` : `HOSTINGER_AI_ROUTER_KEY`, `X_BEARER_TOKEN`, `TWITTERAPI_IO_KEY`, `YOUTUBE_API_KEY`, `APIFY_TOKEN`, `TELEGRAM_API_ID/HASH`, `BSKY_HANDLE/APP_PASSWORD`, `API_TOKEN`, `DATABASE_URL`, `REDIS_URL`
- [ ] Docker Compose : `web` (Next.js), `api` (FastAPI), `workers` (arq), `scheduler`, `postgres` (+pgvector), `redis`, `caddy`
- [ ] Serveur MCP Hostinger branché dans Claude Code ; VPS en template Docker ; domaine gratuit pointé ; HTTPS
- [ ] Smoke test AI Router : un appel Claude (SDK Anthropic, `base_url` à confirmer), `whisper-1`, `text-embedding-3-small`
- ✅ « hello world » Next.js + `/api/health` servis en HTTPS sur le domaine, déployés depuis Claude Code

## S1 : Tests de faisabilité (P0, avant de coder les collecteurs)

- [ ] yt-dlp depuis l'IP du VPS (`/hashtag/<tag>/shorts`, téléchargement audio) ; sinon deno + `bgutil-ytdlp-pot-provider`
- [ ] X : stream filtré avec 2 règles de hashtags + lookup d'auteurs (API officielle) ; TwitterAPI.io en secours
- [ ] Apify : 1 run `clockworks/tiktok-scraper` sur un hashtag ; noter les champs réellement renvoyés
- [ ] CheckFirst `pravda-network` : format du dossier `json/`, fréquence, volume
- [ ] GDELT DOC + Google News RSS sur des mots-clés de l'événement test
- [ ] Classifieur de texte IA `oculus-v2.0-multilingual` : vitesse sur 2 vCPU, premier score sur 500 exemples HC3 French
- [ ] D3lta : installation et vitesse sur 1 000 textes
- ✅ Chaque test consigné dans `docs/spikes.md` (commande, résultat, décision)

## S2 : Tranche 1, événement → X + YouTube → copypasta → salle d'opérations (P0)

- [ ] Modèle `ContentItem` + tables Postgres (items, accounts, clusters, edges, verdicts, events)
- [ ] Agent **Planner** : événement → mots-clés/hashtags FR+EN → validation par le volume réel → `events/<slug>.yaml`
- [ ] Collecteurs X (stream + recherche) et YouTube (API + yt-dlp Shorts), normalisés en `ContentItem`
- [ ] Outils `find_copypasta`, `semantic_clusters`, `detect_bursts` (z-score robuste)
- [ ] API REST + **SSE** (`item.new`, `cluster.updated`, `stats.tick`)
- [ ] Front : écran Lancement (3.1) + salle d'opérations minimale (flux, graphe Sigma, compteurs live)
- ✅ Je tape « manifestations France novembre 2026 » et, en moins de 2 min, le graphe se remplit de vrais posts X et YouTube ; un cluster de textes recopiés apparaît s'il en existe

## S3 : Tranche 2, cross-plateforme (P0)

- [ ] Collecteurs TikTok (Apify), Telegram (canaux publics)
- [ ] `transcribe` (whisper-1 via AI Router) + `ocr_frames` (Claude vision, 3 frames) pour Shorts et TikTok
- [ ] `unshorten_canon`, `fingerprint_media` (pHash sur les frames)
- [ ] `cross_platform_link` : graphe d'empreintes, composantes multi-plateformes, patient zéro, délais
- [ ] Front : **timeline de propagation** (couloirs par plateforme + arcs), sélection synchronisée graphe/flux/timeline
- ✅ Un même contenu vu sur ≥ 2 plateformes forme un cluster, avec patient zéro et arcs dans la timeline

## S4 : Tranche 3, sites web et provenance « Trust the source » (P0)

- [ ] `discover_sites` : GDELT + Google News RSS + liens des posts, filtré par l'événement
- [ ] `lookup_reputation` : base SQLite/Postgres des listes (Iffy, Lin, CheckFirst, VIGINUM, Meta)
- [ ] `site_signals` (RDAP, crt.sh, Wayback CDX, à-propos/mentions/auteurs) + `expand_domain` (dnstwist, IDs GA/GTM/AdSense, urlscan)
- [ ] `d3lta_match` : post ↔ articles découverts et articles Pravda
- [ ] `ai_text_share` (oculus, N ≥ 20) + `provenance_score` (régression logistique calibrée, abstention)
- [ ] API `GET /v1/provenance?target=` + écran **Trust card** (barre en cascade, preuves au survol)
- ✅ Je colle un domaine Pravda : score élevé, critères et preuves visibles. Je colle `lemonde.fr` : score bas. Je colle un domaine inconnu sans données : « données insuffisantes »

## S5 : Tranche 4, agents d'enquête (P0)

- [ ] Boucle d'outils (SDK Anthropic → AI Router) exposant les outils déterministes
- [ ] Triage (`haiku-5.5-eu`) → Enquêteur ⇄ Sceptique (`opus-5.5-eu`) → Juge (`sonnet-5.5-eu`)
- [ ] Validation : un verdict qui cite une preuve absente de l'`evidence` est rejeté ; JSON strict ; techniques DISARM
- [ ] Front : **dossier d'enquête** (preuves côte à côte, débat en deux colonnes relié aux preuves, comptes, Confirmer/Écarter)
- ✅ Sur un cluster réel, le dossier se génère seul en moins de 60 s, et chaque affirmation pointe vers une preuve cliquable

## S6 : Évaluation mesurable (P0, 40 % du barème)

- [ ] Script de téléchargement des jeux (`eval/fetch.py`) : HC3 French, RAID (échantillon), Cresci-2015/2017, Zenodo 13896309 et 23318545, Lin, Iffy
- [ ] Banc d'essai provenance de domaine (split **par réseau**), comptes, texte IA (FR/EN séparés), coordination (essaims injectés + viraux légitimes)
- [ ] Métriques : précision, rappel, FPR + IC de Wilson, AUC bootstrap, calibration (Brier, ECE), matrice de confusion, abstention
- [ ] Front : **onglet Fiabilité** + galerie des erreurs commentées
- ✅ Chaque score affiche ses chiffres sur un jeu jamais vu pendant le réglage, FPR ≤ 2 % au seuil retenu, ou on affiche honnêtement qu'on n'y arrive pas

## S7 : Démo et pitch (P0)

- [ ] Témoins live : articles Pravda de l'heure + comptes officiels (contrôle négatif)
- [ ] Mode **replay** d'une vraie session enregistrée (étiqueté REPLAY)
- [ ] Interface et textes en anglais ; page « Method & Ethics »
- [ ] Script de 3 min + vidéo de secours + README de soumission
- ✅ Démo répétée 3 fois de bout en bout sur l'URL publique

---

## P1 : Gains nets

- [ ] Instagram / Reels (Apify hashtag + profile « About »)
- [ ] **Facebook : pages et groupes publics** via un scraper (Apify), à vérifier (voir SPECS §4). Groupes privés exclus.
- [ ] Bluesky Jetstream + Mastodon (sources gratuites, volume)
- [ ] `score_account` généralisé à toutes les plateformes (+ IsolationForest)
- [ ] `detect_coordination` (co-lien, co-hashtag, co-réponse, à la manière de CooRTweet) + Kleinberg
- [ ] Flux Certificate Transparency : nouveaux domaines liés à l'événement en direct
- [ ] Carte du monde (deck.gl), uniquement des positions réelles
- [ ] Palette ⌘K, replay accéléré dans la timeline
- [ ] Réseau de domaines (écran 3.4)

## P2 : Bonus

- [ ] Empreinte audio (chromaprint) pour les sons réutilisés
- [ ] PDQ/TMK (Meta) en plus du pHash
- [ ] `classify_propaganda` (modèles HF), mesuré sur PTC
- [ ] Extension navigateur affichant la Trust card de la page ouverte
- [ ] Export PDF du dossier d'enquête
