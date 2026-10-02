# Dev container para GitHub Codespaces / VS Code Dev Containers.
# Mismo runtime que Dockerfile.dev (node 22) + python3 para tocar data-engine.
FROM node:22-alpine

RUN apk add --no-cache libc6-compat git python3 py3-pip

WORKDIR /app

# Usuario sin privilegios (Trivy DS-0002).
RUN mkdir -p /app/node_modules /app/.next && chown -R node:node /app
USER node
