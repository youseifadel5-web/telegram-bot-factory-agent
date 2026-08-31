import "dotenv/config";
import express from "express";
import { createServer } from "http";
import net from "net";
import { createExpressMiddleware } from "@trpc/server/adapters/express";
import { registerOAuthRoutes } from "./oauth";
import { registerStorageProxy } from "./storageProxy";
import { appRouter } from "../routers";
import { createContext } from "./context";
import { serveStatic, setupVite } from "./vite";
import { movieConfig } from "@shared/movieConfig";
import { movieFrRequest, normalizeMovies } from "../moviefr";
import { getCatalogCache, putCatalogCache } from "../db";
import { createTelegramBot, getTelegramBot, startTelegramBot } from "../telegramBot";
import { validateTelegramInitData } from "../telegramAuth";

const requestBuckets = new Map<string, { startedAt: number; count: number }>();
function allowMovieRequest(key: string, limit = 30, windowMs = 60_000) {
  const now = Date.now();
  const bucket = requestBuckets.get(key);
  if (!bucket || now - bucket.startedAt >= windowMs) { requestBuckets.set(key, { startedAt: now, count: 1 }); return true; }
  if (bucket.count >= limit) return false;
  bucket.count += 1;
  return true;
}

function isPortAvailable(port: number): Promise<boolean> {
  return new Promise(resolve => {
    const server = net.createServer();
    server.listen(port, () => {
      server.close(() => resolve(true));
    });
    server.on("error", () => resolve(false));
  });
}

async function findAvailablePort(startPort: number = 3000): Promise<number> {
  for (let port = startPort; port < startPort + 20; port++) {
    if (await isPortAvailable(port)) {
      return port;
    }
  }
  throw new Error(`No available port found starting from ${startPort}`);
}

async function startServer() {
  const app = express();
  const server = createServer(app);
  // Configure body parser with larger size limit for file uploads
  app.use(express.json({ limit: "50mb" }));
  app.use(express.urlencoded({ limit: "50mb", extended: true }));
  registerStorageProxy(app);
  registerOAuthRoutes(app);
  createTelegramBot();
  app.post("/api/telegram/validate", (req, res) => {
    const result = validateTelegramInitData(String(req.body?.initData ?? ""));
    return result.valid ? res.json(result) : res.status(401).json({ valid: false, user: null });
  });
  app.get("/api/movies/:id/play", (req, res) => {
    if (!allowMovieRequest(`play:${req.ip}`)) return res.status(429).json({ error: "too many requests" });
    const id = String(req.params.id ?? "").replace(/[^a-zA-Z0-9_-]/g, "");
    if (!id) return res.status(400).json({ error: "invalid movie id" });
    return res.json({ url: `${movieConfig.streamBaseUrl}/play/${encodeURIComponent(id)}` });
  });
  app.get("/api/movies/search", async (req, res) => {
    if (!allowMovieRequest(`search:${req.ip}`)) return res.status(429).json({ message: "too many requests", movies: [] });
    try {
      const query = String(req.query.q ?? "").trim();
      const page = Math.max(1, Number(req.query.page ?? 1));
      if (!query) return res.json({ movies: [], suggestions: [] });
      const cacheKey = `search:${query.toLowerCase()}:${page}`;
      const cached = await getCatalogCache(cacheKey);
      if (cached) return res.json(cached);
      const payload = await movieFrRequest(movieConfig.endpoints.search, { kw: query, pn: page });
      const movies = normalizeMovies(payload);
      const result = { movies, suggestions: movies.slice(0, 5).map((movie) => movie.title) };
      await putCatalogCache(cacheKey, result);
      return res.json(result);
    } catch (error) {
      console.error("[MovieFR] search failed", error);
      return res.status(502).json({ message: "MovieFR search unavailable", movies: [] });
    }
  });
  app.get("/api/movies/:id", async (req, res) => {
    if (!allowMovieRequest(`info:${req.ip}`)) return res.status(429).json({ message: "too many requests" });
    try {
      const payload = await movieFrRequest(movieConfig.endpoints.info, { vod_id: req.params.id });
      return res.json(payload);
    } catch (error) {
      console.error("[MovieFR] info failed", error);
      return res.status(502).json({ message: "MovieFR details unavailable" });
    }
  });
  app.post("/api/telegram/webhook", async (req, res) => {
    try {
      const telegram = getTelegramBot();
      if (!telegram) return res.status(503).json({ message: "BOT_TOKEN is not configured" });
      await telegram.handleUpdate(req.body);
      return res.json({ ok: true });
    } catch (error) {
      console.error("[Telegram] webhook failed", error);
      return res.status(500).json({ ok: false });
    }
  });
  // tRPC API
  app.use(
    "/api/trpc",
    createExpressMiddleware({
      router: appRouter,
      createContext,
    })
  );
  // development mode uses Vite, production mode uses static files
  if (process.env.NODE_ENV === "development") {
    await setupVite(app, server);
  } else {
    serveStatic(app);
  }

  const preferredPort = parseInt(process.env.PORT || "3000");
  const port = await findAvailablePort(preferredPort);

  if (port !== preferredPort) {
    console.log(`Port ${preferredPort} is busy, using port ${port} instead`);
  }

  server.listen(port, async () => {
    console.log(`Server running on http://localhost:${port}/`);
    await startTelegramBot();
  });
}

startServer().catch(console.error);
