# Spikes S1 : tests de faisabilité

Conditions : machine locale, mais **VPS cible simulé** : `taskset -c 0,1` (2 cœurs), `CUDA_VISIBLE_DEVICES=""`,
`OMP_NUM_THREADS=2`, `torch.set_num_threads(2)` / `tf.config.threading.set_intra_op_parallelism_threads(2)`.
Python 3.12, uv 0.9. Scripts et données de test hors projet (scratchpad `spikes/scripts`, `spikes/data`).
Date : 2026-11-14.

---

## Spike 1 : CheckFirst `pravda-network`

### Commandes

```bash
gh api repos/CheckFirstHQ/pravda-network --jq '{size,pushed_at}'
git clone --depth 1 --filter=blob:none https://github.com/CheckFirstHQ/pravda-network.git
gh api "repos/CheckFirstHQ/pravda-network/commits?per_page=20" --jq '.[].commit.committer.date'
gh api "repos/CheckFirstHQ/pravda-network/commits?path=data"          # historique des CSV
curl -sL https://francais.news-pravda.com/rss/news                    # -> 301 vers /rss.xml
```

### Résultats

**Surprise majeure : le dossier `json/` ne contient AUCUN article.** Ce sont des agrégats pour le tableau de bord de CheckFirst.
Le README (qui décrit des CSV `data/*.csv.gz` par article, mis à jour toutes les heures) est **obsolète** : les CSV ont été
supprimés le **2025-06-02** (commit `9eb1754`). Le dernier état avec CSV (`f3f54ad`) contient 46 fichiers, 325 Mo gzip.

- **Contenu actuel** : `README.md` + 89 fichiers `json/<domaine>_viz.json` (de 300 Ko à 820 Ko), **50 Mo** au total dans HEAD.
- **Historique Git : ~42 Go** (`size` API = 42 096 759 Ko), ~13 700 commits. **Ne jamais faire de clone complet.**
- **Fréquence réelle** : 2 commits par jour, à **06:45 et 18:45 UTC** (et non toutes les heures).
- **Volume** : somme des `totalArticles` = **30,6 M articles** depuis 2023 ; ~31 000 articles la veille (2026-11-13) sur l'ensemble du réseau.
  `francais.news-pravda.com` : 981 365 articles au total, ~740 par jour.
- **Domaines** : 89 fichiers, **105 domaines `*.news-pravda.com`** distincts une fois fusionnés les `allDomains` (sans les miroirs
  `*.cdn.ampproject.org`), plus `telegra.ph`.

Format d'un fichier `json/<domaine>_viz.json` (exemple tronqué, `francais.news-pravda.com`) :

```json
{
  "domain": "francais.news-pravda.com",
  "totalArticles": 981365,
  "articlesPerDay":   [{"date": "2023-07-03", "count": 60}, ...],          // 1227 jours
  "topSources":       [{"source": "Telegram: Vbachir", "count": 76246}, ...], // top 1000 sources
  "categories":       [{"category": "world", "count": 795205}, ...],
  "publicationHours": [{"hour": 0, "count": 6517}, ...],
  "sourcesByDay":     [{"date": "2023-07-03", "Telegram: Vbachir": 0, "fr.topwar.ru": 0, ...}, ...], // top 10 sources
  "topSourceNames":   ["Telegram: Vbachir", ...],
  "alternatesStats":  {"articlesWithAlternates": 476689, "percentWithAlternates": 48.57, "avgAlternatesPerArticle": 4.50},
  "languages":        [{"language": "fr", "count": 842827}, ...],
  "languageConnections": [{"source": "ar", "target": "fr", "strength": 3688}, ...],
  "domainLanguageData":  [{"domain": "abkhazia.news-pravda.com", "language": "en", "count": 148}, ...],
  "countryLanguageData": [{"code": "fr", "count": 347354}, ...],
  "allDomains":   ["abkhazia.news-pravda.com", ...],    // 106 entrées (+ variantes ampproject)
  "allLanguages": ["ar", ...]
}
```

Comment extraire :

- **(a) Liste des domaines** : union de `domain` et `allDomains` sur tous les fichiers, filtrer `ampproject` → 105 domaines + `telegra.ph`. OK.
- **(b) Articles récents avec texte ou URL** : **impossible depuis ce dépôt**. Il ne reste que des compteurs (`articlesPerDay`,
  `sourcesByDay`). Alternative testée et fonctionnelle : **le flux RSS de chaque domaine**, `https://<domaine>/rss.xml`
  (`/rss/news` redirige en 301). Pour `francais` : 50 items, **texte complet dans `<content:encoded>`**, titre, lien, `pubDate`, image ;
  23 liens `t.me/...` dans le corps sur 50 items. Mais 50 items ne couvrent que **~33 min** à ce rythme : il faut interroger le
  RSS **toutes les 10-15 min** pour les gros domaines (ou utiliser `sitemap.xml` → `sitemap_news_N.xml.gz` pour rattraper un retard).
  Le flux annonce aussi un hub WebSub (`pubsubhubbub.appspot.com`), non testé.
- **(c) « Source URL » Telegram** : dans `json/`, seulement des **noms** `"Telegram: <handle>"` dans `topSources` (top 1000 par domaine) :
  **7 652 handles Telegram distincts** sur le réseau (top : `llordofwar`, `lomovkaa`, `ostashkonews`, `ukr_2025_ru`, `SolovievLive`),
  plus 1 256 sources web (`tass.ru`, `ria.ru`, `lenta.ru`...). Le handle se convertit en `https://t.me/<handle>` (vérifié sur les
  anciens CSV : `Telegram "russosphere"` ↔ `https://t.me/russosphere`). Pas d'URL de message individuel.
  Dans l'ancien CSV `francais` (366 k lignes, 2023-08 → 2025-05), **78 % des articles venaient de Telegram**, 1 821 canaux distincts.

Ancien format CSV (gelé au 2025-06-02, utile comme corpus historique / jeu de test) :
`URL,Source Title,Source URL,Canonical,OG:Title,OG:Description,Alternates,Country,Publication Date`, récupérable par
`https://raw.githubusercontent.com/CheckFirstHQ/pravda-network/f3f54ad9fdc847031cca8b36a8b204d5e254e751/data/<domaine>.csv.gz`
(49 Mo pour `francais`). Quelques lignes mal échappées (22/366 k) : parser en mode tolérant.

### Synchronisation recommandée

1. Toutes les heures : `git ls-remote https://github.com/CheckFirstHQ/pravda-network refs/heads/main` (1 requête, quelques octets) ;
   ne rien faire si le SHA n'a pas changé (22 h sur 24).
2. Si changé : dans un clone créé une fois avec `git clone --depth 1 --filter=blob:none`, faire
   `git fetch --depth 1 origin main && git reset --hard FETCH_HEAD` (~50 Mo, tous les fichiers changent), puis
   `git gc --prune=now` pour ne pas accumuler. Alternative sans git : `GET /repos/.../git/trees/main?recursive=1` puis
   89 téléchargements `raw.githubusercontent.com` (même volume).
3. Pour le contenu réel : collecteur RSS séparé sur les 105 domaines, toutes les 15 min (5 min pour `francais`, `a.network`,
   `spanish`, `deutsch`...), dédoublonnage par `guid`.

### Problèmes

- README trompeur (CSV et « hourly » n'existent plus) ; le format `json/` n'est pas documenté et peut changer sans préavis.
- Pas de licence explicite sur le dépôt (`license: null`) ; le README demande juste de citer CheckFirst.
- Pas de texte ni d'URL d'article ; les sources Telegram ne sont connues que pour le top 1000 de chaque domaine.

### Décision recommandée : **ADAPTER**

Garder CheckFirst uniquement comme **référentiel** (liste des 105 domaines, ~7 600 canaux Telegram amplifiés, volumes par jour
pour détecter des pics), synchronisé 2×/jour via `ls-remote` + fetch superficiel. Pour les articles, ajouter un **collecteur RSS
`https://<domaine>/rss.xml`** (texte complet disponible). Utiliser l'ancien CSV comme corpus de test (copypasta, entraînement).

---

## Spike 2 : D3lta (VIGINUM)

### Commandes

```bash
uv venv -p 3.12 venv-d3lta && uv pip install -p venv-d3lta/bin/python d3lta   # 138 s, venv = 2,2 Go
uv pip install -p venv-d3lta/bin/python "setuptools<81"                       # correctif obligatoire (voir problèmes)
cd work_d3lta && TFHUB_CACHE_DIR=... taskset -c 0,1 venv-d3lta/bin/python -I scripts/d3lta_bench.py data/texts1000.json
```

Corpus : 1 000 `OG:Description` réelles (FR, ~200 caractères, tronquées « ... ») tirées au hasard parmi les 20 000 plus récentes
de l'ancien CSV CheckFirst `francais` (mai 2025), + 50 doublons injectés : 20 copies exactes, 20 copypastas modifiés
(préfixe « 🔴 URGENT : », ponctuation, hashtags ajoutés), 6 reformulations FR écrites à la main, 4 traductions EN.

### API et sortie

```python
from d3lta.faissd3lta import semantic_faiss
df = pd.DataFrame({"original": texts}); df.index = df.index.astype(str)   # index = identifiants
matches, df_clusters = semantic_faiss(df=df, min_size_txt=20,
    threshold_grapheme=0.693, threshold_language=0.715, threshold_semantic=0.85,
    df_embeddings_use=None,            # ou un DataFrame d'embeddings précalculés (n'importe quel modèle)
    embeddings_to_save="emb",          # pickle des embeddings USE
    remove_matches_same_user=None)     # nom d'une colonne auteur pour ignorer les auto-reprises
```

- `matches` : une ligne par paire, colonnes `source, target, score (cosinus), duplicates, language_source/target,
  text_to_embed_source/target, text_grapheme_source/target, dup_type ∈ {copy-pasta, rewording, translation}, score_lev`.
- `df_clusters` : le DataFrame d'entrée enrichi de `language, text_grapheme, text_to_embed, cluster` (composantes connexes
  networkx, `NaN` si aucun doublon).
- Fonctions de plus bas niveau utilisables pour l'incrémental : `compute_embeddings`, `create_index_cosine` (FAISS IP),
  `index.range_search(...)`, `find_matches`, `compute_duplicate_types`.

### Résultats (2 cœurs CPU)

| Mesure | Valeur |
|---|---|
| `semantic_faiss` sur 1 050 textes, 1er lancement (téléchargement modèles) | 160 s |
| idem, 2e lancement (modèles en cache) | **92,5 s**, dont embeddings 90 s ; langue 0,1 s ; FAISS 0,08 s |
| idem avec embeddings déjà calculés (`df_embeddings_use`) | **0,5 s** |
| Embeddings USE seuls, modèle chargé une fois, batch 100 | **25 textes/s** (1 000 en 40 s), chargement 4,6 s |
| RAM max (process complet) | **2,6 Go** (1,5 Go pour USE seul) |
| Rappel copies exactes / copypastas / traductions | **20/20, 19/20, 4/4** |
| Rappel reformulations, seuil 0,85 (défaut) | **1/6** |
| Rappel reformulations, seuil 0,75 | 6/6, mais les paires « naturelles » passent de 6 à 45 (beaucoup de faux positifs thématiques) |

Les 6 paires naturelles trouvées au seuil par défaut sont de vrais copypastas du réseau (« L'information russe pour les
francophones ! Vous pouvez également suivre... », « abonnez-vous à la nouvelle chaîne @boriskarpovrussie », légendes
« Vidéo: ministère russe de la Défense/TASS#russie ... »). Le copypasta manqué : préfixe + hashtags sur un texte court
font passer la similarité Levenshtein sous 0,693 et le cosinus sous 0,85.

### Dépendances lourdes

- **TensorFlow 2.18 + tensorflow-hub + tensorflow-text** épinglés (versions exactes), + `faiss-cpu==1.9.0.post1`, `fasttext`,
  `gensim`, `scipy==1.12.0`, `pandas==2.2.3`, `networkx==2.8.8`. Venv de 2,2 Go, à isoler du venv PyTorch (conflits probables).
- Modèle d'embeddings : **Universal Sentence Encoder Multilingual Large v3** (TF Hub / Kaggle), **335 Mo** sur disque, 512 dimensions.
- Détection de langue : fastText `lid.176.ftz` (0,9 Mo), téléchargé dans le **répertoire courant**.

### Problèmes

- `import d3lta` plante sans `pkg_resources` : il faut `setuptools<81` (tensorflow-hub 0.16.1).
- `compute_embeddings` **recharge USE et le ré-enregistre (`tf.saved_model.save` → `./use_model_kaggle`, 337 Mo) à chaque appel** :
  ~45 s perdus par appel et écriture disque. Il faut appeler nos propres embeddings et passer `df_embeddings_use`.
- `thread_map(max_workers=8)` par défaut : sur 2 vCPU, contention (90 s dans D3lta contre 40 s en appel direct).
- Pas d'API incrémentale : tout est recalculé sur le lot. Pour un flux, garder un index FAISS persistant et n'appeler
  `compute_duplicate_types` que sur les nouvelles paires.
- Le seuil de reformulation par défaut (0,85) rate la plupart des vraies reformulations ; 0,75 les attrape mais avec beaucoup de bruit.
- Paquet sans licence dans les métadonnées PyPI (le dépôt GitHub est MIT).

### Décision recommandée : **ADAPTER**

Garder la **méthode** D3lta (copypasta = cosinus + Levenshtein sur graphèmes, traduction = langues différentes + cosinus ≥ 0,715,
clusters par composantes connexes), qui marche très bien pour copies, copypastas et traductions. Mais ne pas embarquer TensorFlow
dans le service principal : soit (a) process séparé avec USE chargé une fois et embeddings en cache (25 textes/s ≈ 90 000/h,
suffisant), soit (b) **recommandé** : ré-implémenter les ~100 lignes utiles (ou appeler `semantic_faiss` avec
`df_embeddings_use`) avec **`paraphrase-multilingual-MiniLM-L12-v2`** (PyTorch, voir mesure ci-dessous), en gardant les seuils
par défaut, puis les recalibrer sur un jeu annoté. Option (b) partage le runtime PyTorch avec le détecteur IA.

### Complément : encodeurs PyTorch légers à la place de USE (même corpus de 1 050 textes)

Embeddings calculés avec `sentence-transformers` (2 cœurs, `taskset -c 2,3`, pendant qu'oculus tournait sur les 2 autres cœurs,
donc débit probablement sous-estimé), puis passés à `semantic_faiss(df_embeddings_use=...)` :

| Encodeur | Taille | Débit (2 cœurs) | RAM | Rappel exact/copypasta/reformulation/traduction (seuil 0,85) | Paires « naturelles » |
|---|---|---|---|---|---|
| USE multilingual large (défaut) | 335 Mo | 25 textes/s | 1,5 Go | 20/20, 19/20, 1/6, 4/4 | 6 |
| `paraphrase-multilingual-MiniLM-L12-v2` | 458 Mo (118 M param.) | 17 textes/s | ~1 Go | **20/20, 20/20, 6/6, 4/4** | 17 |
| `multilingual-e5-small` | 470 Mo | 13 textes/s | ~1 Go | 20/20, 20/20, 6/6, 4/4 | **148 673** (inutilisable) |

- MiniLM au seuil 0,85 : les 11 paires « reformulation » naturelles en plus sont en majorité de **vraies reprises de la même
  dépêche** (Trump et Melania aux funérailles, Erdogan qui attrape le doigt de Macron, George Simion / AUR, dette française
  reprise de RIA Novosti), soit exactement les récits coordonnés qu'on cherche ; 2 ou 3 sont seulement du même thème.
  Au seuil 0,80 : 56 paires, trop de bruit.
- e5-small : les cosinus sont tous tassés au-dessus de 0,8 (propriété connue d'e5), donc les seuils D3lta ne s'appliquent pas
  (même à 0,90 : 9 572 paires). Il faudrait des seuils autour de 0,93-0,95, à calibrer. Écarté.
- Piège rencontré : un pickle pandas écrit avec numpy 2 ne se relit pas dans le venv D3lta (numpy 1.x épinglé). Échanger en `.npy`.

---
