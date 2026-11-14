# Déploiement (VPS Hostinger)

**Adresse publique : https://srv2160677.hstgr.cloud**

| | |
|---|---|
| VPS | KVM 2 (2 vCPU, 8 Go), Ubuntu 24.04 avec Docker et Traefik préinstallés |
| IP | 2.25.7.137 |
| Code sur le serveur | `/opt/propaganda-observer` |

## Architecture

```
Internet ─443─► Traefik (préinstallé, réseau hôte, certificats Let's Encrypt)
                  └─► web  (Next.js, :3000) ──► api (FastAPI, :8010) ──► postgres (pgvector) + redis
```

- Seul `web` est publié, via les labels Traefik de `infra/docker-compose.prod.yml`.
- L'API, Postgres et Redis n'ont aucun port ouvert vers l'extérieur. C'est vérifié depuis Internet : 8010, 5432 et 6379 sont fermés.
- L'API exige le jeton interne, que seul le serveur Next possède. La démo publique ne lit que l'instantané publié (voir `docs/acces-et-demo.md`).

## Secrets (sur le serveur uniquement, droits 600, jamais dans git)

| Fichier | Contenu |
|---|---|
| `/opt/propaganda-observer/.env` | Clés de l'API : AI Router, YouTube, Apify, Telegram, Bluesky, `API_TOKEN`, `PSEUDO_KEY`, plafonds de budget |
| `/opt/propaganda-observer/web/.env.production` | `BACKEND_TOKEN` (= `API_TOKEN`), `BETTER_AUTH_SECRET`, `BETTER_AUTH_URL` |
| `/opt/propaganda-observer/.env.compose` | `PG_PASSWORD`, `PUBLIC_HOST` |

`PSEUDO_KEY` doit rester identique à celle utilisée pour les données existantes : sinon, les comptes collectés ensuite ne correspondront plus.

## Mettre à jour

```bash
infra/deploy.sh            # copie le code, reconstruit et relance api et web
infra/deploy.sh web        # seulement l'interface
```

Après une nouvelle collecte, republier la démo depuis la salle d'opérations : bouton « Republish for demo » (compte admin).

## Commandes utiles (sur le serveur)

```bash
cd /opt/propaganda-observer
C="docker compose -f infra/docker-compose.prod.yml --env-file .env.compose"
$C ps                       # état
$C logs -f --tail 50 api    # journaux
$C restart api              # redémarrer un service
$C exec postgres pg_dump -U observer -d observer -Fc > /root/backup-$(date +%F).dump   # sauvegarde
```

## Données initiales

La base (68 Mo) et Redis (cache et compteurs de budget) ont été copiés depuis l'environnement local le 14/11/2026. Le cas France, la publication de la démo, le compte admin et le budget déjà dépensé sont donc identiques.
