#!/usr/bin/env bash
# Met à jour la production : copie le code (sans secrets, caches ni données brutes) puis reconstruit et relance.
# Usage : infra/deploy.sh [service…]   (par défaut : api et web)   ·   Variable : DEPLOY_HOST (défaut root@2.25.7.137)
set -euo pipefail
HOST="${DEPLOY_HOST:-root@2.25.7.137}"
DIR=/opt/propaganda-observer
cd "$(dirname "$0")/.."
tar czf - --exclude=.venv --exclude=node_modules --exclude=.next --exclude=data/raw --exclude='.env*' \
    --exclude=.git --exclude=__pycache__ --exclude='*.tsbuildinfo' . | ssh "$HOST" "tar xzf - -C $DIR"
ssh "$HOST" "cd $DIR && docker compose -f infra/docker-compose.prod.yml --env-file .env.compose up -d --build ${*:-api web} \
    && docker compose -f infra/docker-compose.prod.yml --env-file .env.compose ps --format '{{.Service}} {{.Status}}'"
