# ============================================
# Dockerfile para Frontend Next.js (imagen de PRODUCCION self-hosted)
# ============================================
#
# DUEÑO Y HUECO, dicho para que no acabe en tierra de nadie:
#  - Nadie la DESPLIEGA hoy. El frontend de produccion va en Vercel
#    (vercel.json) y docker-compose.prod.yml no tiene servicio de frontend
#    por eso mismo (auth en MongoDB Atlas, el backend en Oracle). El compose
#    de DESARROLLO usa Dockerfile.dev, no este.
#  - SÍ la CONSUME sbom-scan.yml (fx3): trivy misconfiguration, SBOM y
#    barrido de imagen sobre este fichero, Dockerfile.dev, data-engine/
#    Dockerfile y data-engine/Dockerfile.prod. Borrarla deja un hueco en el
#    pipeline de seguridad.
#  - Para qué existe: la imagen standalone de Next (output: 'standalone')
#    para self-hosting o paridad de build. Si el dia que se cablea en un
#    compose de produccion se decide que sobra, se borra EN EL MISMO cambio
#    que la retire de sbom-scan.yml (son dos trabajos de una decision, no
#    dos decisiones).
# ============================================

# Base fijada por digest del MANIFEST LIST (amd64+arm64): el mismo commit
# construye el mismo SBOM cada día. `node:22-alpine` solo se mueve con un
# build intencionado. Digest de docker buildx imagetools inspect node:22-alpine.
FROM node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402 AS base

# Instalar dependencias solo cuando sea necesario
FROM base AS deps
RUN apk add --no-cache libc6-compat
WORKDIR /app

# Copiar archivos de dependencias
COPY package.json package-lock.json* ./
RUN npm ci

# Builder - compilar la aplicación
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Desactivar telemetría de Next.js
ENV NEXT_TELEMETRY_DISABLED=1

# Build de producción
RUN npm run build

# Runner - imagen final de producción
FROM base AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Crear usuario no-root
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# Copiar archivos necesarios
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
