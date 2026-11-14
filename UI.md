# Propaganda Observer : spécifications de l'interface

> Objectif : un effet « waouh » pendant la démo, avec une salle d'opérations qui observe le monde en direct, dans l'esprit de Palantir Gotham.
> Ni tableau de bord générique, ni esthétique « slop IA ». Tout ce qui est affiché est **réel et en direct**, sans aucune donnée décorative.

---

## 1. Direction artistique

**Ce qu'on cherche** : une console d'analyste. Sombre, dense, précise, calme. La donnée est la décoration. L'effet « waouh » vient du **mouvement des vraies données** (graphe qui se forme, contenu qui saute d'un réseau à l'autre), pas des effets visuels.

**Interdits anti-slop :**
- dégradés violet/bleu, glassmorphism, halos lumineux, fonds « aurora » ;
- emoji, icônes ✨, « Powered by AI », mascotte, illustrations 3D ;
- cartes arrondies à grosse ombre, pastels, coins à 16 px et plus ;
- textes marketing dans l'application ; on écrit comme un analyste (« 14 comptes · 3 plateformes · fenêtre 4 min ») ;
- graphiques ou cartes avec des données factices de remplissage ; un panneau vide affiche « en attente de données ».

**Principes :**
- une couleur d'accent, les autres teintes sont des gris ; la couleur sert **uniquement** à porter du sens (verdict, plateforme, sélection) ;
- lignes de 1 px, coins à 2-4 px, grille stricte, densité élevée ;
- chiffres en police à chasse fixe et tabulaire, horodatages UTC partout ;
- mouvement fonctionnel : une animation = un événement de donnée réel.

### Tokens

| Token | Valeur | Usage |
|---|---|---|
| `--bg` | `#0A0C0F` | Fond |
| `--panel` | `#101318` | Panneaux |
| `--line` | `#1D222A` | Bordures, grille |
| `--text` | `#D3D9E0` | Texte principal |
| `--muted` | `#6B7480` | Libellés, axes |
| `--accent` | `#E8A33D` (ambre) | Sélection, focus, alerte « à examiner » |
| `--critical` | `#E5484D` | « À examiner en priorité » |
| `--organic` | `#5C6670` | « Probablement organique » (gris, volontairement neutre) |
| Plateformes | Teintes désaturées : YouTube `#C4554D`, TikTok `#4FB3BF`, Instagram `#B5679B`, Bluesky `#4A8FD9`, Mastodon `#7C6FD1`, Telegram `#3E9BC4`, Web `#9AA3AD` | Nœuds, couloirs de la timeline |

Un thème clair n'est pas prioritaire ; on assume le mode sombre de « salle d'opérations ».

**Typographie** : IBM Plex Sans (UI) + IBM Plex Mono (données, horodatages, identifiants). Taille de base 13 px, interligne serré.

## 2. Stack front

| Besoin | Choix | Pourquoi |
|---|---|---|
| Framework | **Next.js** (App Router, TypeScript, dernière version stable), `output: "standalone"` | Demandé ; déploiement Docker simple sur le VPS |
| Style | Tailwind CSS + tokens CSS ci-dessus ; primitives Radix (via shadcn/ui **restylé**, jamais le look par défaut) | Accessibilité sans le style générique |
| Graphe | **Sigma.js + graphology** (WebGL), ForceAtlas2 dans un Web Worker | Des milliers de nœuds fluides, mise en page qui « respire » en direct |
| Carte du monde | **deck.gl + MapLibre GL**, fond sombre (CARTO Dark Matter ou Protomaps) | Arcs animés, couches par plateforme |
| Timeline / courbes | **visx** (D3 sous React) | Contrôle total, rendu sobre |
| Animation | Motion (ex-Framer Motion), avec parcimonie | Entrées de panneaux, transitions de sélection |
| Données live | **SSE** depuis FastAPI (`/stream/events/<slug>`) + TanStack Query pour le reste | Simple, robuste derrière Caddy |
| Palette de commandes | `cmdk` (⌘K) | Effet console d'analyste |
| État | Zustand (sélection partagée entre graphe, carte, timeline et inspecteur) | Une sélection = tous les panneaux se synchronisent |

## 3. Écrans

### 3.1 Lancement : « Nouvelle observation »
- Un seul champ, centré, en grand : *« Décrivez un événement… »* (ex. « manifestations en France, novembre 2026 »). À côté, la liste live **Google Trends FR** : un clic lance une observation.
- Après validation, le Planner déroule sa réflexion **en direct**, ligne par ligne en mono : mots-clés générés, puis vérification du volume réel par source, chacun avec une **sparkline réelle** et un statut retenu ou écarté.
- Les mots-clés sont des puces modifiables. Le bouton « Lancer la surveillance » démarre les collecteurs, et on bascule sur la salle d'opérations.

### 3.2 Salle d'opérations (écran principal, celui de la démo)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ● LIVE  manifestations-nov-2026   12 431 items · 6 plateformes · 3 alertes   ⌘K│
├───────────────┬──────────────────────────────────────────┬───────────────────┤
│ FLUX          │                                          │ INSPECTEUR        │
│ (posts entrants│        GRAPHE (Sigma, plein centre)      │ (sélection        │
│ par plateforme,│   nœuds = comptes / contenus / domaines  │  courante :       │
│ défilement)   │   arêtes = empreintes partagées           │  compte, cluster, │
│               │   [onglet] CARTE (deck.gl)                │  domaine)         │
├───────────────┴──────────────────────────────────────────┴───────────────────┤
│ TIMELINE DE PROPAGATION : un couloir par plateforme, arcs entre couloirs     │
│ YouTube   ──●────●●───────────                                                │
│ TikTok    ────●●●●●──── ↖ même audio, 9 comptes, Δ 2 min                      │
│ Telegram  ●─────────────  (patient zéro)                                      │
└──────────────────────────────────────────────────────────────────────────────┘
```

- **Graphe** :
  - Les nœuds sont colorés par plateforme. Leur taille suit l'audience, et leur contour (ambre ou rouge) suit le verdict.
  - Les nouveaux nœuds apparaissent avec un léger fondu, puis la mise en page se réorganise en direct.
  - Les clusters détectés s'entourent d'une **enveloppe convexe** fine.
  - Filtres par type de lien : texte, sens, image, son, lien, article.
- **Carte** : uniquement des positions **réelles**.
  - Sources : pays de chaîne YouTube (`snippet.country`), pays des domaines (géolocalisation IP/ASN), pays déclarés par CheckFirst.
  - Des arcs animés relient la source d'un contenu à ses reprises.
  - Si la position est inconnue, le point n'est pas dessiné.
- **Timeline de propagation** : c'est la **signature visuelle** du projet.
  - Un couloir par plateforme.
  - Quand une empreinte relie deux posts sur deux réseaux, un arc est tracé entre les couloirs.
  - On voit un contenu naître sur Telegram puis éclater sur TikTok en 2 minutes.
  - Un curseur permet de rejouer la séquence.
- **Flux** : posts entrants, sur une ligne chacun : plateforme, heure, extrait, puis des badges d'empreinte quand ils rejoignent un cluster.
- **Alertes** : un nouveau cluster « à examiner » s'affiche en bandeau discret en haut, avec un clic pour ouvrir le dossier. Pas de son, pas de popup.

### 3.3 Dossier d'enquête (un cluster)
- **En-tête** :
  - verdict ;
  - confiance ;
  - techniques DISARM, en étiquettes mono ;
  - chiffres clés : comptes, plateformes, fenêtre, patient zéro.
- **Preuves côte à côte** :
  - les médias comparés (frames extraites alignées, distance pHash affichée) ;
  - les textes avec les passages identiques surlignés ;
  - les transcriptions et les textes OCR ;
  - la forme d'onde audio pour un son réutilisé.
- **Débat des agents** : deux colonnes, *Enquêteur* et *Sceptique*. Chaque affirmation renvoie par un lien à la preuve (`evidence_id`) qui la justifie, et le survol met la preuve en surbrillance. Le *Juge* conclut en bas. C'est ce qui rend l'explicabilité **visible**, et le jury note l'explicabilité.
- **Comptes** : tableau dense avec âge, ratio, cadence et score, et les **features expliquées** en mini-barres.
- **Actions** : Confirmer / Écarter (revue humaine), Exporter le dossier (JSON + PDF).

### 3.4 Réseau de domaines
- Graphe centré sur un domaine : sosies (dnstwist), sous-domaines (crt.sh), identifiants Google Analytics/AdSense partagés, IP/ASN.
- Chaque arête est typée et l'outil qui l'a trouvée est indiqué.
- Les posts sociaux qui pointent vers ces domaines sont visibles.

### 3.5 Fiabilité
- Pour chaque score (provenance de domaine, compte, texte IA, coordination) : précision, rappel, **taux de faux positifs** avec intervalles de Wilson, courbe précision-rappel, diagramme de calibration, matrice de confusion, taux d'abstention, galerie des erreurs commentées (voir SPECS §8).
- Seuils actuels, et faux positifs écartés par la revue humaine.
- Message : « on sait quand on se trompe ».

### 3.6 Trust card (« Trust the source »)
- Accessible depuis le champ de l'écran de lancement (coller une URL, un domaine ou un compte) et via ⌘K.
- En-tête : cible, **score 0-100** en grand chiffre mono, bande de confiance (intervalle), mention « données insuffisantes » si abstention.
- **Barre en cascade** des contributions : chaque critère (âge, clonage, typosquat, réseau GA/IP, IA, amplification) pousse le score vers le haut ou le bas. Survol = preuve brute (date RDAP, identifiant GA, paire de textes surlignée, part IA avec N).
- Mini-graphe du réseau du domaine et liste des comptes qui l'amplifient (clic = bascule dans la salle d'opérations).
- Pied de fiche : version du modèle, date des listes, précision et FPR du score (lien vers l'onglet Fiabilité), avertissement « priorise une vérification, ne condamne pas ».

## 4. Micro-interactions qui font l'effet « waouh » (toutes adossées à de la vraie donnée)

1. **Ouverture de session** : l'écran passe du noir à la grille, puis aux compteurs qui démarrent avec les premiers posts réels.
2. **Formation d'un cluster** : les nœuds concernés se rapprochent dans le graphe, l'enveloppe se dessine, et l'arc apparaît dans la timeline au même moment.
3. **Sélection synchronisée** : un clic sur un compte met en surbrillance ses posts dans le flux, son point sur la carte, ses arcs dans la timeline et sa fiche dans l'inspecteur.
4. **⌘K** : « aller au cluster 7 », « ouvrir domaine x.com », « rejouer les 30 dernières minutes ».
5. **Replay** : la timeline se rejoue en accéléré et le graphe se reconstruit dans l'ordre chronologique. C'est le moment fort de la démo.

## 5. Performance et robustesse

- Le graphe est limité à environ 5 000 nœuds visibles. Au-delà, on agrège par cluster et on peut déplier.
- Le SSE se reconnecte automatiquement. Le bandeau « LIVE » passe à « RECONNEXION » s'il est coupé.
- **Mode secours démo** : rejouer une session réelle enregistrée (`/replay/<session>`). Ce sont de vraies données capturées plus tôt, clairement étiquetées « REPLAY ». On l'utilise seulement si le réseau tombe pendant la démo.
- Lighthouse au-dessus de 90 sur la page de lancement. Test sur un écran 1920×1080, celui du projecteur.

## 6. Déploiement

- Conteneur `web` (Next.js standalone) ajouté au Docker Compose du VPS Hostinger, derrière Caddy (HTTPS automatique). `/api` et `/stream` sont relayés vers FastAPI.
- Variables : `NEXT_PUBLIC_API_URL`, token d'accès.

## 7. Arborescence proposée

```
web/
  app/
    page.tsx                  # Lancement (3.1)
    ops/[slug]/page.tsx       # Salle d'opérations (3.2)
    case/[clusterId]/page.tsx # Dossier (3.3)
    domain/[domain]/page.tsx  # Réseau de domaines (3.4)
    trust/page.tsx            # Trust card (3.6), ?target=<url|domaine|compte>
    reliability/page.tsx      # Fiabilité (3.5)
  components/
    graph/  map/  timeline/  feed/  inspector/  evidence/  debate/  command/
  lib/ stream.ts  store.ts  api.ts  tokens.css
```

---

# v2 — refonte (14/11/2026), remplace les sections 1 à 4 ci-dessus

Inspirations documentées : Blackbird.AI Narrative Details (ordre de lecture), Hoaxy (couleur des liens = position, des nœuds = risque), CooRnet (graphe projeté comptes ↔ comptes), Maltego (graphe + tableau synchronisé), Linkurious (file de cas triée), NewsGuard (fiche de récit), Cambridge Intelligence (plafond de nœuds, légende permanente).

**Thème clair. Une couleur = une seule information :**

| Information | Encodage |
|---|---|
| Sévérité (alertes) | Priority rouge `--sev-priority`, Review ambre `--sev-review`, Organic gris `--sev-organic` |
| Position vs récit | Reprend violet ▲ `--st-promotes`, Dément sarcelle ✓ `--st-debunks`, Neutre ardoise ● `--st-neutral` |
| Plateforme | badges texte monochromes (WEB, BSKY, YT, TT, IG, TG), jamais de couleur |
| Interaction | bleu `--accent` uniquement |

**Écrans** (`web/components/ops/`) : barre de filtres globale persistante (plateformes, position, sévérité) +
- **Brief** : fiche du récit repliable, compteurs, activité par jour (empilée par position ou par plateforme), petits multiples par plateforme, histoires à examiner, principaux amplificateurs.
- **Stories** : file triée par sévérité + détail (sévérité → position citée → chiffres → sections repliables : pourquoi, propagation, comptes, réseau de l'histoire, publications avec % de similarité de sens, méthode).
- **Network** : graphe projeté comptes ↔ comptes (lien = même histoire, épaisseur = nb d'histoires, couleur = position), nœud = risque du compte, communautés nommées, légende repliable, tableau synchronisé, double-clic = fiche.
- **Accounts** : tableau triable avec indicateurs de risque expliqués ; tiroir latéral par compte.

Données : `observer/api/views.py` (`/summary`, `/stories/{id}`, `/network`, `/accounts`, `/accounts/{id}`).
