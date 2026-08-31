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
import { createTelegramBot, getTelegramBot, startTelegramBot } from "../telegramBot";

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
  app.get("/api/movies/search", async (req, res) => {
    try {
      const query = String(req.query.q ?? "").trim();
      if (!query) return res.json({ movies: [], suggestions: [] });
      const payload = await movieFrRequest(movieConfig.endpoints.search, { kw: query, pn: Number(req.query.page ?? 1) });
      const movies = normalizeMovies(payload);
      return res.json({ movies, suggestions: movies.slice(0, 5).map((movie) => movie.title) });
    } catch (error) {
      console.error("[MovieFR] search failed", error);
      return res.status(502).json({ message: "MovieFR search unavailable", movies: [] });
    }
  });
  app.get("/api/movies/:id", async (req, res) => {
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
    if (process.env.TELEGRAM_MODE === "polling") await startTelegramBot();
  });
}

startServer().catch(console.error);
