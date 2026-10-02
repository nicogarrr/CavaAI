# Dev container para GitHub Codespaces / VS Code Dev Containers.
# Mismo runtime que Dockerfile.dev (node 22) + python3 para tocar data-engine.
# Base fijada por digest del MANIFEST LIST (amd64+arm64): ver Dockerfile.
FROM node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402

RUN apk add --no-cache libc6-compat git python3 py3-pip

WORKDIR /app
