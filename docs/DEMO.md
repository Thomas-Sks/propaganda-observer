# Script de démo (3 min) — Propaganda Observer

**Cas réel** : campagne pro-russe « chambres de torture d'Azov » près de Kyiv (novembre 2026), documentée par Kyiv Independent, Al Jazeera, Demagog, NewsGuard, Antibot4Navalny. Observation : `azov-torture-chambers-nov-2026`.

| Temps | Écran | Ce qu'on dit / montre |
|---|---|---|
| 0:00 | Accueil `/` | « Disinformation spreads across platforms faster than anyone can read it. Observer watches a narrative live and explains, with evidence, what looks coordinated. » Cliquer l'exemple Azov → le Planner génère les termes en 5 langues, chacun vérifié sur le volume réel. |
| 0:30 | Ops · **Brief** | 6 plateformes en direct. Le graphique : **PEAK le 3/11** (85 publications contre 18 d'habitude), puis les démentis arrivent. Compteurs : X narratifs reprennent la fausse affirmation, Y la démentent. |
| 1:00 | **Narratives** | Ouvrir le narratif *Priority* (3 sites Pravda, même texte en ES/DE/FR en 2 min). « Why this verdict » : chaque signal a un poids et une phrase. Lancer **AI investigation** : l'enquêteur bâtit le dossier, le sceptique cherche une explication organique, le juge tranche ; cliquer une référence [P2] → la preuve s'allume. Technique DISARM affichée. |
| 1:45 | **Network** | Hubs = narratifs (violet = reprend, sarcelle = dément), comptes autour, **ponts** entre narratifs. ▶ **Replay** : on voit la campagne naître le 2-3/11 puis les fact-checkers arriver. Double-clic sur un site Pravda → fiche du compte (source listée VIGINUM/CheckFirst). |
| 2:15 | **Trust card** `/trust` | Coller `thewashingtonexaminer.net` (faux site Storm-1516) puis `tagesschau.de` : score de provenance expliqué, preuves brutes (âge du domaine, sosie…), abstention si données insuffisantes. API `/v1/provenance` = service pour hébergeurs (Hostinger). |
| 2:40 | **Reliability** `/reliability` | « We measure every detector on labelled data it never saw while tuning » : précision, rappel, **taux de faux positifs** avec intervalles de confiance, et la galerie des erreurs. « Not just the happy path. » |
| 3:00 | — | Limites assumées : pas de X (API payante), position jugée par LLM mais toujours citée, données Twitter pour l'évaluation des bots. |

**Plan B** : si le réseau tombe, les données de l'observation sont en base ; tous les écrans fonctionnent hors ligne sauf la collecte et l'enquête non encore en cache (lancer l'enquête sur 2-3 narratifs avant la démo pour la mettre en cache). Prévoir une capture vidéo de ce parcours.

**Budget** : enquête ≈ 0,05 $ par narratif (cache ensuite) ; collecte TikTok/Instagram ≈ 0,15 $ par passe (1 par heure max).
