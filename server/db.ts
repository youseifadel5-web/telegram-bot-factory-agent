import { eq } from "drizzle-orm";
import { drizzle } from "drizzle-orm/mysql2";
import { InsertUser, users, favorites, watchHistory, catalogCache } from "../drizzle/schema";
import { ENV } from './_core/env';

let _db: ReturnType<typeof drizzle> | null = null;

// Lazily create the drizzle instance so local tooling can run without a DB.
export async function getDb() {
  if (!_db && process.env.DATABASE_URL) {
    try {
      _db = drizzle(process.env.DATABASE_URL);
    } catch (error) {
      console.warn("[Database] Failed to connect:", error);
      _db = null;
    }
  }
  return _db;
}

export async function upsertUser(user: InsertUser): Promise<void> {
  if (!user.openId) {
    throw new Error("User openId is required for upsert");
  }

  const db = await getDb();
  if (!db) {
    console.warn("[Database] Cannot upsert user: database not available");
    return;
  }

  try {
    const values: InsertUser = {
      openId: user.openId,
    };
    const updateSet: Record<string, unknown> = {};

    const textFields = ["name", "email", "loginMethod"] as const;
    type TextField = (typeof textFields)[number];

    const assignNullable = (field: TextField) => {
      const value = user[field];
      if (value === undefined) return;
      const normalized = value ?? null;
      values[field] = normalized;
      updateSet[field] = normalized;
    };

    textFields.forEach(assignNullable);

    if (user.lastSignedIn !== undefined) {
      values.lastSignedIn = user.lastSignedIn;
      updateSet.lastSignedIn = user.lastSignedIn;
    }
    if (user.role !== undefined) {
      values.role = user.role;
      updateSet.role = user.role;
    } else if (user.openId === ENV.ownerOpenId) {
      values.role = 'admin';
      updateSet.role = 'admin';
    }

    if (!values.lastSignedIn) {
      values.lastSignedIn = new Date();
    }

    if (Object.keys(updateSet).length === 0) {
      updateSet.lastSignedIn = new Date();
    }

    await db.insert(users).values(values).onDuplicateKeyUpdate({
      set: updateSet,
    });
  } catch (error) {
    console.error("[Database] Failed to upsert user:", error);
    throw error;
  }
}

export async function getUserByOpenId(openId: string) {
  const db = await getDb();
  if (!db) {
    console.warn("[Database] Cannot get user: database not available");
    return undefined;
  }

  const result = await db.select().from(users).where(eq(users.openId, openId)).limit(1);

  return result.length > 0 ? result[0] : undefined;
}

export async function getCatalogCache(cacheKey: string) {
  const db = await getDb();
  if (!db) return undefined;
  const result = await db.select().from(catalogCache).where(eq(catalogCache.cacheKey, cacheKey)).limit(1);
  const row = result[0];
  return row && row.expiresAt.getTime() > Date.now() ? JSON.parse(row.payload) : undefined;
}

export async function putCatalogCache(cacheKey: string, payload: unknown, ttlMs = 120_000) {
  const db = await getDb();
  if (!db) return;
  const serialized = JSON.stringify(payload);
  const expiresAt = new Date(Date.now() + ttlMs);
  await db.insert(catalogCache).values({ cacheKey, payload: serialized, expiresAt }).onDuplicateKeyUpdate({ set: { payload: serialized, expiresAt, updatedAt: new Date() } });
}

export async function listFavorites(userId: number) {
  const db = await getDb();
  return db ? db.select().from(favorites).where(eq(favorites.userId, userId)) : [];
}

export async function toggleFavorite(userId: number, movie: { id: string; title: string; poster?: string }) {
  const db = await getDb();
  if (!db) return { saved: false };
  const existing = await db.select().from(favorites).where(eq(favorites.userId, userId));
  const match = existing.find((item) => item.movieId === movie.id);
  if (match) { await db.delete(favorites).where(eq(favorites.id, match.id)); return { saved: false }; }
  await db.insert(favorites).values({ userId, movieId: movie.id, movieTitle: movie.title, posterUrl: movie.poster ?? null });
  return { saved: true };
}

export async function listWatchHistory(userId: number) {
  const db = await getDb();
  return db ? db.select().from(watchHistory).where(eq(watchHistory.userId, userId)) : [];
}

export async function upsertWatchHistory(userId: number, movie: { id: string; title: string }, progressSeconds = 0) {
  const db = await getDb();
  if (!db) return;
  const existing = await db.select().from(watchHistory).where(eq(watchHistory.userId, userId));
  const match = existing.find((item) => item.movieId === movie.id);
  if (match) await db.update(watchHistory).set({ movieTitle: movie.title, progressSeconds, watchedAt: new Date() }).where(eq(watchHistory.id, match.id));
  else await db.insert(watchHistory).values({ userId, movieId: movie.id, movieTitle: movie.title, progressSeconds });
}
