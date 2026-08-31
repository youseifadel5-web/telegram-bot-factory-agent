import { int, mysqlEnum, mysqlTable, text, timestamp, varchar, uniqueIndex } from "drizzle-orm/mysql-core";

/**
 * Core user table backing auth flow.
 * Extend this file with additional tables as your product grows.
 * Columns use camelCase to match both database fields and generated types.
 */
export const users = mysqlTable("users", {
  /**
   * Surrogate primary key. Auto-incremented numeric value managed by the database.
   * Use this for relations between tables.
   */
  id: int("id").autoincrement().primaryKey(),
  /** Manus OAuth identifier (openId) returned from the OAuth callback. Unique per user. */
  openId: varchar("openId", { length: 64 }).notNull().unique(),
  name: text("name"),
  email: varchar("email", { length: 320 }),
  loginMethod: varchar("loginMethod", { length: 64 }),
  role: mysqlEnum("role", ["user", "admin"]).default("user").notNull(),
  createdAt: timestamp("createdAt").defaultNow().notNull(),
  updatedAt: timestamp("updatedAt").defaultNow().onUpdateNow().notNull(),
  lastSignedIn: timestamp("lastSignedIn").defaultNow().notNull(),
});

export type User = typeof users.$inferSelect;
export type InsertUser = typeof users.$inferInsert;

export const favorites = mysqlTable("favorites", {
  id: int("id").autoincrement().primaryKey(),
  userId: int("userId").notNull(),
  movieId: varchar("movieId", { length: 128 }).notNull(),
  movieTitle: varchar("movieTitle", { length: 255 }).notNull(),
  posterUrl: text("posterUrl"),
  createdAt: timestamp("createdAt").defaultNow().notNull(),
}, (table) => ({ userMovie: uniqueIndex("favorites_user_movie").on(table.userId, table.movieId) }));

export const watchHistory = mysqlTable("watch_history", {
  id: int("id").autoincrement().primaryKey(),
  userId: int("userId").notNull(),
  movieId: varchar("movieId", { length: 128 }).notNull(),
  movieTitle: varchar("movieTitle", { length: 255 }).notNull(),
  progressSeconds: int("progressSeconds").default(0).notNull(),
  watchedAt: timestamp("watchedAt").defaultNow().onUpdateNow().notNull(),
}, (table) => ({ userMovie: uniqueIndex("history_user_movie").on(table.userId, table.movieId) }));

export type Favorite = typeof favorites.$inferSelect;
export type WatchHistory = typeof watchHistory.$inferSelect;

export const catalogCache = mysqlTable("catalog_cache", {
  id: int("id").autoincrement().primaryKey(),
  cacheKey: varchar("cacheKey", { length: 255 }).notNull().unique(),
  payload: text("payload").notNull(),
  expiresAt: timestamp("expiresAt").notNull(),
  updatedAt: timestamp("updatedAt").defaultNow().onUpdateNow().notNull(),
});

export type CatalogCache = typeof catalogCache.$inferSelect;