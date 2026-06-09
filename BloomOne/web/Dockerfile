# ── Stage 1: Dependencies ────────────────────────────────────────────────
FROM node:22-alpine AS deps
WORKDIR /app

COPY package.json package-lock.json ./
COPY prisma ./prisma/
RUN npm ci && npm cache clean --force

# ── Stage 2: Build ───────────────────────────────────────────────────────
FROM node:22-alpine AS builder
WORKDIR /app

COPY package.json package-lock.json ./
COPY prisma ./prisma/
RUN npm ci

COPY . .

# Build args become env vars at build time
ARG BLOOMONE_API_URL
ARG BLOOMONE_API_KEY
ARG DATABASE_URL

ENV BLOOMONE_API_URL=${BLOOMONE_API_URL}
ENV BLOOMONE_API_KEY=${BLOOMONE_API_KEY}
ENV DATABASE_URL=${DATABASE_URL}

RUN npx prisma generate && npx prisma db push --accept-data-loss && npm run build

# ── Stage 3: Run ─────────────────────────────────────────────────────────
FROM node:22-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV UPLOADS_DIR=/app/data/uploads

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs && \
    mkdir -p /app/data/uploads && \
    chown -R nextjs:nodejs /app/data


COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

# Copy Prisma engine for runtime queries
COPY --from=builder /app/node_modules/.prisma ./node_modules/.prisma
COPY --from=builder /app/node_modules/@prisma ./node_modules/@prisma
COPY --from=builder /app/prisma ./prisma

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
