# Propaganda Observer : spécifications, détection live et cross-plateforme

> Challenge Junction × Hostinger : détecter la propagande coordonnée, l'amplification par bots et les acteurs malveillants.
> Barème : qualité de détection 40 % · exécution technique et déploiement live sur Hostinger 25 % · originalité et impact 20 % · clarté de la démo.
> Contrainte d'équipe : **tout tourne en live sur de vraies données.** Les essaims synthétiques ne servent qu'à mesurer le rappel, jamais à la démo principale.
> Projet neuf, écrit de zéro dans ce dossier.
> Sous-thème visé en plus : **« Trust the source »** — noter la provenance d'une page ou d'un compte (âge du domaine, contenu cloné, texte IA, réseaux de liens), de façon **transparente et mesurable** (précision et taux de faux positifs publiés, pas seulement le cas qui marche).
> Recherches sources : 8 recherches web du 14/11/2026 (accès plateformes dont X, outils GitHub, listes de domaines, provenance et évaluation). Les statuts sont datés de ce jour.
> Budget : les API de données (X, Apify, etc.) sont budgétées, avec les essais gratuits en complément. Exception : **pas de détecteur de texte IA payant**.
> Langue : interface et pitch **en anglais** (jury international) ; ces specs restent en français.

---

## 1. Vision en une phrase

On saisit un événement en texte libre, par exemple « les manifestations en France en novembre ». Le système trouve lui-même les mots-clés et hashtags, surveille en direct YouTube/Shorts, TikTok, Instagram, Bluesky, Mastodon, Telegram et les sites web, puis **repère le même contenu republié d'une plateforme à l'autre**. Il en sort un verdict expliqué, avec des preuves cliquables.

En plus, n'importe qui peut coller une URL, un domaine ou un compte et obtenir une **fiche de provenance** (« Trust card ») : un score expliqué critère par critère, dont la fiabilité est mesurée et affichée.

## 2. Parcours utilisateur (scénario de démo)

### A. Surveiller un événement

1. **Entrée** : l'utilisateur tape un événement (ou clique sur un sujet qui explose dans Google Trends FR).
2. **Expansion par le LLM** (étape *Planner*) : il produit une configuration d'événement (`events/<slug>.yaml`) :
   - mots-clés en français et en anglais, variantes, hashtags probables, slogans, noms propres ;
   - fenêtre temporelle et pays ;
   - **chaque mot-clé est validé par les données** : on garde ceux qui ont du volume réel (RSS Trends, nombre de résultats sur YouTube et Bluesky), on écarte les autres ;
   - l'utilisateur peut éditer la liste avant de lancer.
3. **Lancement du workflow** : les collecteurs démarrent en parallèle. Le dashboard se remplit en direct (posts/min par plateforme, pics).
4. **Détection** : les outils déterministes tournent par lots de 2 à 5 min et produisent des **clusters de contenu** et des **clusters de comptes**.
5. **Enquête** : sur chaque cluster au-dessus du seuil, l'agent *Enquêteur* rassemble les preuves et l'agent *Sceptique* cherche une explication organique. Le verdict est rattaché aux techniques **DISARM**.
6. **Restitution** : la carte de propagation cross-plateforme montre qui a publié en premier, où, et comment le contenu s'est répandu. On voit la fiche du cluster, les preuves et le niveau de confiance, et un humain peut confirmer ou écarter.

### B. Vérifier une source (« Trust the source »)

1. L'utilisateur colle une URL, un domaine ou un compte (X, TikTok, YouTube, Instagram, Bluesky, Telegram).
2. Les outils déterministes calculent les critères du §3bis (âge, clonage, IA, réseau, amplification).
3. La **Trust card** affiche le score de provenance 0-100, la contribution de chaque critère avec sa preuve, le niveau de confiance, et « données insuffisantes » si trop de critères manquent.
4. Liens directs : les sites du même réseau, l'article d'origine du contenu cloné, les comptes qui l'amplifient (on rebascule dans le parcours A).

Même moteur exposé en **API pour Hostinger** : `GET /v1/provenance?target=<url|domaine|compte>` → JSON (score, features, preuves, version du modèle). Cas d'usage : l'équipe abus d'un hébergeur vérifie si un site hébergé appartient à un réseau de propagande connu.

## 3. Détection cross-plateforme (cœur de l'originalité)

**Idée** : chaque contenu, quelle que soit la plateforme, est ramené à un **objet commun** porteur d'empreintes comparables. Deux posts sur deux réseaux sont « le même contenu » s'ils partagent au moins une empreinte forte.

### 3.1 Modèle commun `ContentItem`

| Champ | Contenu |
|---|---|
| `platform`, `post_id`, `url`, `ts` | Identité et date de publication |
| `author_pseudo` | Hash salé (pseudonymisation dès l'ingestion) |
| `text` | Légende ou post |
| `transcript` | Audio transcrit (faster-whisper), pour les vidéos |
| `ocr_text` | Texte incrusté (EasyOCR sur 3 frames), pour les vidéos et images |
| `urls_canon` | Liens déroulés et canonicalisés (sans UTM, eTLD+1) |
| `hashtags` | Hashtags du post |
| `fp_text` | Signature MinHash du texte, de la transcription et de l'OCR |
| `fp_embed` | Embedding multilingue (`paraphrase-multilingual-MiniLM-L12-v2`, fastembed/ONNX, CPU) |
| `fp_image[]` | pHash/PDQ des images ou frames |
| `fp_audio` | Chromaprint, pour retrouver un son réutilisé |
| `account_meta` | Âge, abonnés, abonnements, nombre de posts : ce que la plateforme donne |

### 3.2 Empreintes et liens cross-plateforme

| Lien | Empreinte | Force |
|---|---|---|
| Même texte | MinHash Jaccard ≥ 0,6 sur `text` + `transcript` + `ocr_text` | Forte |
| Même sens (paraphrase, traduction) | Cosinus d'embedding ≥ seuil calibré | Moyenne |
| Même visuel | Distance de Hamming pHash/PDQ ≤ seuil | Forte |
| Même son | Correspondance chromaprint | Forte (attention : les sons tendance sont légitimes, à pondérer) |
| Même lien | `urls_canon` identique, ou domaine du même réseau (§3.3) | Forte |
| Même article source | D3lta (VIGINUM) entre un post et un article web | Forte |

Les liens forment un graphe biparti contenus ↔ comptes. Un **cluster cross-plateforme** est une composante qui touche au moins 2 plateformes.

**Ce qu'on en tire** :
- **Patient zéro** : la publication la plus ancienne et sa plateforme d'origine.
- **Chaîne de propagation** : délais entre plateformes. Une reprise en moins de 2 min sur 4 réseaux suggère une orchestration, une reprise sur 6 h suggère une diffusion organique.
- **Signature de l'opérateur** : les mêmes pseudos ou motifs de pseudo sur plusieurs plateformes. Comme signal faible seulement.

### 3.3 Sites web dans la boucle

**Les sites sont découverts à partir de l'événement, pas tirés d'une liste fixe.** Les listes connues (Pravda, Doppelganger, Storm-1516, Paperwall, Iffy…) sont un **critère du score**, pas la source.

Découverte en continu (outil `discover_sites`) :
1. **Google News RSS** (✅ testé : 100 items en 1,5 s ; domaine source en clair dans `<source url>` ; URL réelle décodable avec `googlenewsdecoder` si besoin). Biais : ne voit que ce que Google indexe.
2. **Fichiers GDELT toutes les 15 min** (✅ testé : `data.gdeltproject.org/gdeltv2/lastupdate.txt` → GKG ≈ 2,6 Mo zippé), filtrés en local par mots-clés et URL. La DOC API GDELT est **non fiable** (429 et réponses vides) : option avec cache seulement.
3. **Longue traîne hors Google** : Brave Search API, Exa ou Tavily (offres gratuites, non testés).
4. **Liens partagés dans les posts sociaux** de l'événement (déroulés, canonicalisés) : principal canal d'amplification de Storm-1516 et Doppelganger, et remonte des domaines que Google n'indexe pas.
5. **Certificate Transparency** : `certstream-server-go` **auto-hébergé** sur le VPS (le serveur public CaliDog ne répond plus), filtré par mots-clés de l'événement et ressemblance avec des noms de médias. crt.sh en complément, par domaine uniquement (pas de recherche par sous-chaîne).
6. Le LLM ajoute aux mots-clés des **variantes typosquat** des médias susceptibles d'être imités.
7. Chaque domaine découvert (domaine enregistrable, dédoublonné) passe dans `provenance_score` ; les articles récupérés alimentent `find_copypasta` / `d3lta_match`.

**Listes de réseaux connus (features)** : CheckFirst Pravda (✅ mise à jour toutes les heures, domaines tirés des noms de fichiers `json/*_viz.json`), Storm-1516 (✅ `dszalkowski/storm-1516`, liste .txt issue du rapport VIGINUM, dernière mise à jour 06/2025), Meta CIB/Doppelganger (✅ CSV `facebook/threat-research/indicators/csv`, dont H1 2026), CopyCop (Recorded Future, annexes PDF à parser), Paperwall (Citizen Lab, 123 domaines dans le rapport), Iffy, Lin et al.

- Les liens présents dans les posts sont comparés à la **base de réputation** (§5, outil `lookup_reputation`).
- **Sans lien** : la transcription ou l'OCR d'une vidéo est comparée par D3lta et MinHash au texte des articles découverts pour l'événement et à ceux des réseaux connus (dont Pravda via CheckFirst, mis à jour toutes les heures). Une vidéo TikTok qui lit un article Pravda est donc détectée même sans URL.
- **Expansion** : un domaine suspect trouvé en live lance `expand_domain` (sosies, sous-domaines, identifiants Google Analytics partagés) et révèle le réseau de sites derrière.

### 3.4 Garde-fous contre les faux positifs (40 % du barème)

- Une seule empreinte ne suffit jamais. Il faut **au moins 2 types de liens indépendants**, ou 1 lien fort et des comptes atypiques.
- **Liste blanche** : comptes officiels, médias reconnus (score Lin/Iffy élevé), communiqués et dépêches AFP repris légitimement, sons tendance.
- Niveaux de verdict : `probablement organique` / `à examiner` / `à examiner en priorité`. **Aucun verdict « fabriqué » sans revue humaine.**
- Le Sceptique doit produire une hypothèse organique et la tester avec les outils avant que le verdict passe à « prioritaire ».

## 3bis. Score de provenance (« Trust the source »)

**Modèle** : régression logistique sur des features binaires ou bornées, **coefficients publiés** dans l'interface. Score = σ(β₀ + Σ βᵢxᵢ), recalibré par régression isotonique sur un jeu de validation. Les poids ci-dessous sont des **valeurs de départ**, réapprises sur les jeux étiquetés du §8.

**Domaine / page** (hiérarchie d'indicateurs reprise d'Information Laundromat) :

| Feature | Poids initial | Outil |
|---|---|---|
| Identifiant GA/GTM/AdSense, certificat TLS ou IP partagé avec un domaine listé (indicateur « conclusif ») | +3,0 | `expand_domain`, `lookup_reputation` |
| Contenu cloné : MinHash Jaccard ≥ 0,8 avec un domaine listé, ou appariement D3lta | +2,0 | `find_copypasta`, `d3lta_match` |
| Sosie typosquatté d'un média (dnstwist) | +2,0 | `expand_domain` |
| Domaine de moins de 6 mois (RDAP) ou premier certificat crt.sh de moins de 6 mois | +1,0 | `site_signals` |
| Pas de page « à propos », de mentions légales ni d'auteurs signés | +0,8 | `site_signals` |
| Part d'articles détectés IA ≥ 50 % (sur au moins 20 articles de plus de 300 mots) | +0,7, plafonné | `ai_text_share` |
| Moins de 3 captures Wayback | +0,5 | `site_signals` |
| WHOIS masqué | +0,3 (très fréquent chez les sites légitimes) | `site_signals` |
| Indicateurs « associatifs » (CDN, méta-balises, DOM, CMS, images proches) | +0,3 chacun, plafonné à +1 | `expand_domain` |
| Amplifié par un cluster coordonné détecté (parcours A) | +1,0 | `cross_platform_link` |

**Compte social** : âge (ou date de la plus ancienne publication si l'âge n'est pas fourni), ratio abonnés/abonnements, publications par jour, historique de changements de nom, pseudo en chiffres, photo par défaut, entropie des horaires, part de posts recopiés depuis d'autres comptes, part de réponses coordonnées, part de textes IA (sur au moins 20 posts), appartenance à un cluster.

**Règles de transparence :**
- chaque critère est affiché avec sa contribution et la preuve brute (date RDAP, identifiant GA, paire de textes…) ;
- **abstention** : « données insuffisantes » s'il manque plus de 3 critères ;
- le score sert à **prioriser une vérification**, ce n'est pas un verdict ; c'est écrit sur la fiche ;
- version du modèle et date de figement des listes affichées.

**Texte généré par IA : signal faible, assumé comme tel.** Les détecteurs ouverts sont fragiles : à 1 % de faux positifs, Binoculars détecte 58 % des textes IA et Fast-DetectGPT 49 %, et seulement 14 % / 7 % sur GPT-4o, avec un rappel plus faible en français (arXiv 2412.05139). Donc :
- jamais de verdict sur un texte isolé ou court ; uniquement une **part** agrégée sur au moins 20 textes d'une même source (approche Hanley & Durumeric, *Machine-Made Media*, ICWSM 2024) ;
- détecteur : **open source uniquement, aucun service payant**, sur CPU — `danibor/oculus-v2.0-multilingual` (DeBERTa) mesuré sur HC3 French ; Fast-DetectGPT exclu (l'AI Router n'expose pas les logprobs des tokens d'entrée) ;
- poids plafonné, et son TPR à 1 % de FPR **mesuré sur nos propres données FR et EN** est affiché.

## 4. Sources de données (état au 14/11/2026)

| Plateforme | Méthode retenue | Signal compte | Coût | Statut |
|---|---|---|---|---|
| Google Trends | RSS `trends.google.com/trending/rss?geo=FR`, interrogé toutes les 10 min (+ `trendspy` pour les séries, à retester depuis le VPS) | — | Gratuit | ✅ testé |
| YouTube + **Shorts** | API Data v3 (`search.list` limité à 100 appels/jour, le reste à 1 unité sur 10 000/jour) + yt-dlp `/hashtag/<tag>/shorts`, playlist `UUSH…` par chaîne, test `/shorts/<id>` (200 pour un Short, 303 sinon) | **Date de création de chaîne**, abonnés, cadence | Gratuit | ✅ testé en résidentiel, ⚠️ VPS à tester |
| TikTok | Apify `clockworks/tiktok-scraper` (≈ 1,70 $/1 000) ; EnsembleData en synchrone (50 unités/jour gratuites) ; Creative Center via un acteur Apify pour les hashtags tendance | Abonnés, abonnements, nombre de vidéos (âge estimé par la plus ancienne vidéo) | ≈ 20-50 $ au total | 🟡 à brancher |
| Instagram / Reels | Apify `instagram-hashtag-scraper` + `instagram-profile-scraper` (option « About » : date d'inscription) | Abonnés, abonnements, posts, date d'inscription | Inclus ci-dessus | 🟡 à brancher |
| Facebook (P1) | **Pages et groupes publics uniquement**, via un scraper (Apify ou Bright Data), à vérifier. Graph API sans recherche publique, Meta Content Library réservée aux chercheurs. **Groupes privés exclus** : y entrer avec de faux comptes reviendrait à de l'infiltration, contraire aux CGU, et les opinions politiques sont des données sensibles (RGPD art. 9) | Selon le scraper | Crédits Apify | ❓ à vérifier |
| X / Twitter | **Abandonné (décision du 14/11)** : API officielle trop chère, pas de crédit gratuit utilisable ; scrapers tiers écartés aussi. On l'annonce comme limite au jury. | — | — | ❌ hors périmètre |
| Bluesky | Jetstream (live, sans compte) + search (compte gratuit) | Complet | Gratuit | 🟡 à brancher |
| Mastodon | `/timelines/tag` (sans compte) | Âge, abonnés | Gratuit | 🟡 à brancher |
| Telegram | Canaux publics (Telethon / `telegram-mcp`), amorcés par les « Source URL » de CheckFirst | Abonnés du canal | Gratuit | 🟡 |
| Web | Listes de domaines (§5) + liens extraits des posts + CheckFirst `json/` | — | Gratuit | 🟡 |

**Non retenu en 48 h** : TikTok Research API, Meta Content Library, YouTube Researcher Program et DSA article 40 (délais de 4 semaines à 3 mois). On les cite dans le pitch comme « voie de production conforme ». pytrends est archivé. L'API Instagram Graph renvoie au plus 30 hashtags/7 jours et sans auteur. Pour X : twikit cassé depuis mars 2026, snscrape mort, Nitter instable ; twscrape fonctionne mais exige des comptes (bannissables). Les CGU de X (9/10/2026) interdisent le scraping et prévoient 15 000 $ par million de posts au-delà d'1 M/24 h : on reste sur l'API officielle par défaut.

## 5. Outils déterministes exposés aux agents

Règle : **les outils détectent, le LLM orchestre et explique.** Chaque outil est une fonction Python pure (seeds, seuils et versions fixés) qui renvoie `{result, evidence: [ids, scores], params}`. Le LLM n'a le droit de citer que l'`evidence`.

| # | Outil | Implémentation |
|---|---|---|
| 1 | `find_copypasta(items) -> clusters` | datasketch MinHash LSH + vérification RapidFuzz |
| 2 | `semantic_clusters(items) -> clusters` | Embeddings multilingues : fastembed en local (CPU) ; `text-embedding-3-small` via l'AI Router en alternative |
| 3 | `detect_coordination(actions, window_s) -> graph` | Algorithme CooRTweet réimplémenté avec networkx (co-lien, co-hashtag, co-réponse) |
| 4 | `detect_bursts(series) -> intervals` | Z-score robuste (médiane/MAD) + Kleinberg (≈ 60 lignes) + `ruptures` |
| 5 | `score_account(meta) -> {score, features}` | Features explicables + IsolationForest, normalisées pour toutes les plateformes |
| 6 | `fingerprint_media(path) -> {phash[], pdq, audio_fp}` | ffmpeg (3 frames) + imagehash/pdqhash + chromaprint |
| 7 | `transcribe(path)` / `ocr_frames(path)` | **Par API via l'AI Router** : `whisper-1` (variante `-eu`) pour l'audio ; Claude (vision) en température 0 pour le texte incrusté sur 3 frames. Pas de charge sur le VPS |
| 8 | `cross_platform_link(items) -> graph` | Graphe d'empreintes du §3.2, composantes multi-plateformes, patient zéro |
| 9 | `unshorten_canon(url) -> url` | Suivi des redirections + canonicalisation |
| 10 | `lookup_reputation(domain) -> {label, score, sources}` | SQLite fusionnant CheckFirst Pravda, VIGINUM Portal Kombat, Meta threat-research, Iffy, Lin et al. |
| 11 | `d3lta_match(texts, articles) -> pairs` | VIGINUM-FR/D3lta |
| 12 | `expand_domain(domain) -> graph` | dnstwist + API crt.sh + regex GA/GTM/AdSense + urlscan.io + whoisit (RDAP) + Wayback CDX |
| 13 | `classify_propaganda(text) -> techniques` | Modèles HF (QCRI Prta, IDA-SERICS). **Signal, jamais preuve** |
| 14 | `site_signals(domain) -> {rdap_age, ct_first_seen, wayback_count, whois_private, has_about, has_legal, has_authors}` | whoisit, API crt.sh, Wayback CDX, parsing HTML |
| 15 | `ai_text_share(texts) -> {share, n, detector, tpr_at_1fpr}` | Classifieur open source sur CPU (`danibor/oculus-v2.0-multilingual` à mesurer), agrégation sur N ≥ 20. Fast-DetectGPT impossible via l'AI Router (pas de logprobs des tokens d'entrée) |
| 17 | `discover_sites(keywords, since) -> domains[]` | Google News RSS + fichiers GDELT 15 min + liens des posts + certstream-server-go (+ Brave/Exa/Tavily en option) (§3.3) |
| 16 | `provenance_score(target) -> {score, features[], evidence[], abstain, model_version}` | Régression logistique calibrée du §3bis, sur les sorties des outils 1, 9-12, 14, 15 |

Exposition : un **serveur MCP « observer-tools »** (FastMCP) qui réutilise les serveurs existants pour la collecte : `apify/apify-mcp-server`, `chigwell/telegram-mcp`, SDK `atproto`.

## 6. Agents

| Agent | Rôle | Modèle |
|---|---|---|
| **Planner** | Transforme l'événement en mots-clés et hashtags, les valide contre les volumes réels et écrit la config d'événement | `claude-sonnet-5.5-eu` |
| **Collector** (déterministe, pas un LLM) | Planifie les collecteurs et les quotas (budget YouTube, crédits Apify) | — |
| **Triage** | Résume chaque nouveau cluster et décide si on enquête | `claude-haiku-5.5-eu` |
| **Enquêteur** | Appelle les outils 6 à 12, construit le dossier de preuves et la chaîne de propagation | `claude-opus-5.5-eu` |
| **Sceptique** | Formule et teste les hypothèses organiques (événement réel, dépêche reprise, son tendance, fan-club) | `claude-opus-5.5-eu` |
| **Juge** | Fusionne les deux dossiers, fixe le niveau et les techniques DISARM, rédige l'explication | `claude-sonnet-5.5-eu` |

**Implémentation des agents** : appels directs à l'API (SDK Anthropic en Python, `base_url` = AI Router Hostinger), boucle d'outils maison sur nos fonctions Python. Pas de framework : les agents sont peu nombreux, les outils sont en Python, et un seul langage côté back simplifie tout. Mastra (TypeScript) écarté car il imposerait un second runtime et une passerelle vers les outils Python. Noms tirés du catalogue public de l'AI Router (`GET https://router.hostinger.com/v1/models`, 168 modèles) ; variantes `-eu` pour la résidence des données (argument RGPD). Tool use disponible ; streaming à tester sur les modèles Claude.

Le verdict est un JSON strict : `{level, confidence, disarm_ttps[], evidence_ids[], organic_hypotheses_tested[], summary_fr}`. Un verdict qui cite une preuve absente de l'`evidence` est rejeté automatiquement.

## 7. Architecture et déploiement Hostinger

```
[Saisie événement] → Planner → events/<slug>.yaml
                                   │
          ┌────────────── Scheduler (APScheduler) ───────────────┐
          │  Trends RSS · YouTube API · yt-dlp Shorts · Apify      │
          │  TikTok/IG · Jetstream · Mastodon · Telegram · CheckFirst│
          └───────────────┬───────────────────────────────────────┘
                          ▼
      Normalisation ContentItem → workers médias (whisper, OCR, pHash, chromaprint)
                          ▼
      SQLite → Postgres + pgvector (si le temps) ── outils déterministes (lots de 2-5 min)
                          ▼
      Triage → Enquêteur ⇄ Sceptique → Juge → verdicts
                          ▼
      API FastAPI (REST + SSE) → front Next.js (salle d'opérations : graphe, carte, timeline) — voir UI.md
```

- **Ressources fournies par Hostinger (1 mois)** : VPS KVM 2 (2 vCPU, 8 Go RAM, 100 Go NVMe, Docker, domaine gratuit), **AI Router** (une clé, 150+ modèles dont Anthropic, compatible SDK Anthropic/OpenAI), AI Builder, et **Connector/API/CLI MCP** pour déployer depuis l'éditeur.
- **AI Router** : `base_url` OpenAI = `https://router.hostinger.com/v1` ; SDK Anthropic : essayer `https://router.hostinger.com` (endpoint `/v1/messages` présent). Auth `Bearer sk-hstgr-…` (hPanel → AI Router). Expose : chat + tool use, vision, `whisper-1`, `text-embedding-3-small/large`, batches.
- **MCP Hostinger** : `claude mcp add --transport http hostinger https://mcp.hostinger.com` (OAuth) ; opérations `vps_docker_create` (déploie un docker-compose), `vps_firewall_*`, `dns_records_*`.
- Conséquences : pas de LLM local 7B (Binoculars exclu) ; transcription et OCR par API ; seul le classifieur de texte IA et les embeddings locaux tournent sur le CPU ; template VPS Docker avec images Python.
- **VPS Hostinger KVM 2**, avec Docker Compose : `web` (Next.js), `api`, `workers`, `scheduler`, `bgutil-pot-provider`, `caddy` (HTTPS).
- **Interface** : Next.js, style « salle d'opérations », spécifiée dans [`UI.md`](UI.md).
- **Risque n°1** : YouTube bloque yt-dlp depuis une IP de datacenter. Plan : deno + `bgutil-ytdlp-pot-provider`, sinon un worker médias sur une machine de l'équipe ou derrière un proxy résidentiel. **À tester dans la première heure.**
- Accès protégé par un token d'API.

## 8. Qualité de détection : comment on la prouve (40 % du barème + « transparent et mesurable »)

Principe : **chaque score a sa vérité terrain, son jeu de test jamais vu pendant le réglage, et ses chiffres publiés dans l'onglet Fiabilité**, y compris les échecs.

| Score | Positifs | Négatifs | Précaution |
|---|---|---|---|
| Provenance de domaine | Iffy (CSV, ≈ 2 040 domaines, CC BY 4.0) + CheckFirst Pravda, VIGINUM Portal Kombat, Doppelganger (`meta/threat-research`) | Lin et al. `domain_pc1.csv` (11 520 domaines notés 0-1) avec pc1 ≥ 0,8 + médias FR/EN reconnus | **Découpage train/test par réseau** (cluster d'identifiants/IP), jamais par domaine, sinon les identifiants partagés font fuiter les labels. MBFC seulement en comparaison secondaire (licence restrictive). |
| Compte | Cresci-2017 (466 Mo) et Cresci-2015 (232 Mo), téléchargement direct depuis le Bot Repository | Comptes humains de ces jeux | Données Twitter uniquement : limite à annoncer pour Bluesky/Mastodon (aucun jeu étiqueté trouvé). TwiBot-22 exclu (accès sur demande). |
| Coordination (comptes) | Coordinated Reply Attacks (Zenodo 13896309, CC-BY-4.0, ≈ 4,9 Go) | Information Operations Honduras/UAE (Zenodo 23318545, CC-BY-4.0) : comptes authentiques du même sujet = **mesure directe des faux positifs** | Repère publié : AUC 0,88 (tweets) / 0,97 (comptes). |
| Texte IA | **HC3 French OOD** (`almanach/hc3_french_ood`, FR + EN, CC-BY-SA-4.0) + RAID (`liamdugan/raid`, EN, 11 générateurs) ou COLING 2025 multilingue (40+ générateurs, sans FR) | idem | Rapporter TPR à 1 % et 5 % de FPR, en EN et en FR séparément. |
| Techniques de propagande (option) | PTC SemEval-2020 tâche 11 (Zenodo 3952415, EN) | — | Aucun jeu FR accessible directement (SemEval-2023 sur inscription) : limite annoncée. |
| Coordination / cross-plateforme | Essaims injectés (copie, paraphrase, traduction, vidéo réencodée/recadrée, comptes vieillis étalés) | Contenus viraux légitimes : dépêche AFP reprise, son tendance, communiqué officiel, fan-club | Les essaims synthétiques mesurent le rappel ; **les cas viraux légitimes mesurent les faux positifs**. |

**Tous ces jeux sont téléchargeables directement (liens testés le 14/11/2026), sans formulaire ni approbation.**

**Ce que montre l'onglet Fiabilité :**
- précision, rappel et **taux de faux positifs** au seuil retenu (cible FPR ≤ 2 %), avec intervalles de Wilson ; AUC avec bootstrap (1 000 rééchantillonnages) ;
- courbe précision-rappel et **diagramme de calibration** (10 classes), Brier score et ECE ;
- matrice de confusion, **taux d'abstention**, et une **galerie des faux positifs et faux négatifs** commentés (ex. média local récent sous WHOIS masqué) ;
- taille, provenance et date de figement de chaque jeu ; version du modèle ;
- avertissement : le score priorise une vérification, il ne condamne pas.

**Témoins positifs live** (pour que la démo ne dépende pas de la chance) :
- articles du réseau Pravda publiés dans l'heure (CheckFirst) et leurs reprises Telegram / réseaux : vraie propagande documentée, disponible en continu ;
- bots déclarés (Bluesky, X `verified_type`/automatisé) comme témoins du score de compte ;
- témoins négatifs live : comptes officiels et médias reconnus, qui doivent sortir « organique ».

## 9. Confidentialité et conformité

- Pseudonymisation à l'ingestion (hash salé), identités séparées et purgées, expiration à 30 jours.
- Médias téléchargés supprimés une fois les empreintes calculées.
- Respect minimal des CGU : petits échantillons, scraping délégué aux fournisseurs (Apify), pas de comptes jetables en production.
- Les listes de domaines sans licence (VIGINUM, Lin, CheckFirst) sont citées et non redistribuées.

## 10. Plan de travail (indicatif)

| Créneau | Collecte | Détection | Agents | Front / déploiement |
|---|---|---|---|---|
| H0-4 | Test yt-dlp depuis le VPS, crédits Apify, clé YouTube | Modèle `ContentItem` + stockage | Prompt Planner | VPS + Docker + HTTPS |
| H4-16 | YouTube/Shorts, Apify TikTok/IG, X (API officielle), RSS Trends, Bluesky | Outils 1, 2, 4, 6, 7, 9, 10 | Serveur MCP d'outils | Saisie événement + flux live |
| H16-30 | Telegram, Mastodon, CheckFirst | Outils 3, 5, 8, 11, 12, 14-16 + jeux d'évaluation | Enquêteur + Sceptique + Juge | Carte de propagation |
| H30-40 | Robustesse, cache, quotas | Évaluation (§8), calibration | Validation des preuves | Onglet Fiabilité + Trust card + API `/v1/provenance` |
| H40-48 | Gel | Calibration des seuils | Répétition de la démo | Démo live + vidéo de secours |

## 11. Questions ouvertes

- Score du détecteur de texte IA open source (oculus) sur HC3 French : décide son poids.
- Brave / Exa / Tavily et Media Cloud : non testés ; à essayer pour la longue traîne.
- certstream-server-go sur le VPS : à déployer et mesurer (volume, CPU).
- Base_url exacte pour le SDK Anthropic sur l'AI Router, et streaming des modèles Claude.
- Vitesse des embeddings et du classifieur de texte IA sur 2 vCPU.
- Catalogue et noms de modèles de l'AI Router Hostinger.
- yt-dlp depuis le VPS : à tester dès la première heure.

## Annexe : dépôts et liens

- Collecte : `apify/apify-mcp-server`, `yt-dlp/yt-dlp`, `bgutil-ytdlp-pot-provider`, `MarshalX/atproto`, `bluesky-social/jetstream`, `chigwell/telegram-mcp`
- Texte : `ekzhu/datasketch`, `rapidfuzz/RapidFuzz`, `VIGINUM-FR/D3lta`, `deepcharles/ruptures`, `nicolarighetti/CooRTweet` (algorithme)
- Médias : `SYSTRAN/faster-whisper`, `JaidedAI/EasyOCR`, `JohannesBuchner/imagehash`, `meta/ThreatExchange` (PDQ/TMK), `faustomorales/pdqhash-python`, `acoustid/chromaprint`
- Domaines : `elceef/dnstwist`, crt.sh, `meeb/whoisit`, `urlscan/urlscan-python`, `bellingcat/wayback-google-analytics`, `Institute-for-Strategic-Dialogue/information-laundromat`, `dhn/udon`
- Listes : `CheckFirstHQ/pravda-network` (dossier `json/`, mis à jour toutes les heures), `VIGINUM-FR/Rapports-Techniques`, `meta/threat-research`, Iffy.news, `hauselin/domain-quality-ratings`
- Cadres : DISARM Framework ; évaluation : TwiBot-22, Zenodo 13896309
- Outillage OSINT MCP : `OpenOSINT/OpenOSINT`, `soxoj/awesome-osint-mcp-servers`, `civictechdc/cib-mango-tree`
- Collecte Mastodon : API publique `/api/v1/timelines/tag/<tag>`
- X : docs.x.com (pricing pay-per-use, filtered stream, rate limits), TwitterAPI.io, SocialData.tools, `vladkens/twscrape`
- Provenance : `ASD-at-GMF/disinfo-laundromat` (hiérarchie d'indicateurs), W3C Credible Web signals, Hanley & Durumeric *Machine-Made Media* (arXiv 2305.09820)
- Texte IA : `baoguangsheng/fast-detect-gpt`, `ahans30/Binoculars`, `danibor/oculus-v2.0-multilingual`, `liamdugan/raid`, évaluation indépendante arXiv 2412.05139, NBER w34223
- Évaluation : `almanach/hc3_french_ood`, `liamdugan/raid`, Cresci-2015/2017 (botometer.osome.iu.edu/bot-repository), Zenodo 13896309 + `osome-iu/io-coordinated-replies`, Zenodo 23318545, `hauselin/domain-quality-ratings`, Iffy CSV, Zenodo 3952415 (PTC)
- Hostinger : `router.hostinger.com/v1/models`, `github.com/hostinger/api-mcp-server`
