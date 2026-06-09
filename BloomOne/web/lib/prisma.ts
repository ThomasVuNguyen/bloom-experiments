/**
 * Prisma Client singleton for Next.js.
 *
 * Prisma 7 requires a driver adapter for database connections.
 * Uses @prisma/adapter-pg for PostgreSQL.
 *
 * In development, hot-reloading can create multiple PrismaClient instances
 * which exhausts database connections. This singleton prevents that.
 */

import { PrismaPg } from "@prisma/adapter-pg";
import { PrismaClient } from "@prisma/client";

const globalForPrisma = globalThis as unknown as { prisma: PrismaClient };

function createPrismaClient(): PrismaClient {
  const adapter = new PrismaPg({
    connectionString: process.env.DATABASE_URL!,
  });

  return new PrismaClient({
    adapter,
    log: process.env.NODE_ENV === "development" ? ["warn", "error"] : ["error"],
  });
}

export const prisma = globalForPrisma.prisma || createPrismaClient();

if (process.env.NODE_ENV !== "production") {
  globalForPrisma.prisma = prisma;
}
