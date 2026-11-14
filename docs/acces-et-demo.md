# Accès, rôles et données de démonstration

## Qui voit quoi

| Accès | Pour qui | Peut faire |
|---|---|---|
| **Admin**, connecté (Better Auth) | Juges Hostinger, équipe | Tout : créer une observation (Planner, LLM), collecter en direct (Apify, YouTube…), lancer des enquêtes IA, **publier pour la démo** |
| **Démo publique**, sans compte | Tout le monde | Lire **uniquement les données publiées**. Aucun appel externe, aucun appel payant, aucun calcul |

- La page de connexion (`/login`) propose aussi un bouton « Explore the public demo ». Le site est consultable sans compte.
- L'inscription publique est désactivée. Le compte admin est créé par `web/scripts/setup-auth.mjs`, qui crée aussi les tables Better Auth dans le Postgres du projet :

  ```bash
  cd web && node --env-file=.env.local scripts/setup-auth.mjs
  ```

  Les identifiants (`ADMIN_EMAIL`, `ADMIN_PASSWORD`) sont dans `web/.env.local`, qui n'est pas versionné.
- **Sessions simultanées.** Chaque connexion admin crée sa propre session en base. Plusieurs juges peuvent être connectés en même temps sur le même compte, et la déconnexion de l'un ne touche pas les autres.
- **Limite de connexion** : 30 essais par minute et par IP. Les juges peuvent se connecter ensemble depuis le même réseau, et la force brute reste freinée.

## Chemin d'une requête

```
navigateur ──► Next.js /backend/* ──(jeton interne + rôle)──► FastAPI
               ├ session admin vérifiée en base à chaque appel
               └ sans session = démo publique : lecture seule, pas de flux temps réel
```

- FastAPI refuse toute requête sans `x-internal-token` (sauf `/api/health`). Il ne doit donc pas être exposé publiquement : seul Next.js le joint.
- Pour la démo publique (rôle `demo`), FastAPI ne sert **que** la table `snapshots`. Un chemin non publié renvoie 404, sans aucun calcul.
- **Garde-fou supplémentaire** : dans une requête démo, `llm.READ_ONLY` est actif. Toute création de client LLM ou d'embeddings lève `ReadOnly`, si bien que même un bug ne peut rien coûter.

## Publier pour la démo

Dans la salle d'opérations d'une observation, un admin clique **« Publish for demo »** (ou « Republish »). Le serveur fige alors, en 1 à 2 minutes :

- toutes les vues de l'observation : résumé, narratifs, réseau, coordination, thèmes, comptes, comptes suspects ;
- la fiche de chaque narratif et de chaque compte ;
- les enquêtes IA **déjà faites** : la publication n'en lance aucune nouvelle. Lancez d'abord les enquêtes voulues en admin ;
- la page Reliability et les cartes de provenance d'exemple de la page Trust card.

Une republication remplace l'instantané précédent d'un bloc. Les observations visibles par le public sont celles qui ont été publiées.

Équivalent en API (admin) : `POST /api/events/{slug}/publish`, puis `GET /api/events/{slug}/publication` pour suivre l'état.
