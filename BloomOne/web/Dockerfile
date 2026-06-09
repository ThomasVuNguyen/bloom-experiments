# ── Stage 1: Dependencies ────────────────────────────────────────────────
FROM node:22-alpine AS deps
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --only=production && npm cache clean --force

# ── Stage 2: Build ───────────────────────────────────────────────────────
FROM node:22-alpine AS builder
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Build args become env vars at build time
ARG BLOOMONE_API_URL
ARG BLOOMONE_API_KEY

ENV BLOOMONE_API_URL=${BLOOMONE_API_URL}
ENV BLOOMONE_API_KEY=${BLOOMONE_API_KEY}

RUN npm run build

# ── Stage 3: Run ─────────────────────────────────────────────────────────
FROM node:22-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV CHATS_DIR=/app/data/chats
ENV FILES_DIR=/app/data/files
ENV UPLOADS_DIR=/app/data/uploads

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs && \
    mkdir -p /app/data/chats /app/data/files /app/data/uploads && \
    chown -R nextjs:nodejs /app/data


COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
