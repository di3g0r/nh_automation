# Prod image: build the static React app, then serve it (and proxy /api,
# /plc) with Caddy over internal HTTPS (overview §3, §8).
#
# Built with the repository root as context (see deploy/docker-compose.prod.yml)
# so it can also pick up deploy/Caddyfile.
FROM node:22-alpine AS build

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/. .
RUN npm run build

FROM caddy:2-alpine

COPY --from=build /app/dist /srv
COPY deploy/Caddyfile /etc/caddy/Caddyfile

EXPOSE 443 80
