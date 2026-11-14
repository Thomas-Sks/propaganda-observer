# Interface Next.js 16 (build de production).
FROM node:24-slim AS build
RUN corepack enable
WORKDIR /web
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm build

FROM node:24-slim
WORKDIR /web
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000
COPY --from=build /web ./
USER node
EXPOSE 3000
# Next lancé directement par Node : aucun téléchargement (corepack/pnpm) au démarrage du conteneur
CMD ["node", "node_modules/next/dist/bin/next", "start"]
