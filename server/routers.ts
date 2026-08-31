import { COOKIE_NAME } from "@shared/const";
import { getSessionCookieOptions } from "./_core/cookies";
import { systemRouter } from "./_core/systemRouter";
import { publicProcedure, protectedProcedure, router } from "./_core/trpc";
import { z } from "zod";
import { listFavorites, listWatchHistory, toggleFavorite, upsertWatchHistory } from "./db";

export const appRouter = router({
    // if you need to use socket.io, read and register route in server/_core/index.ts, all api should start with '/api/' so that the gateway can route correctly
  system: systemRouter,
  auth: router({
    me: publicProcedure.query(opts => opts.ctx.user),
    logout: publicProcedure.mutation(({ ctx }) => {
      const cookieOptions = getSessionCookieOptions(ctx.req);
      ctx.res.clearCookie(COOKIE_NAME, { ...cookieOptions, maxAge: -1 });
      return {
        success: true,
      } as const;
    }),
  }),

  library: router({
    favorites: protectedProcedure.query(({ ctx }) => listFavorites(ctx.user.id)),
    toggleFavorite: protectedProcedure.input(z.object({ id: z.string(), title: z.string(), poster: z.string().optional() })).mutation(({ ctx, input }) => toggleFavorite(ctx.user.id, input)),
    history: protectedProcedure.query(({ ctx }) => listWatchHistory(ctx.user.id)),
    recordHistory: protectedProcedure.input(z.object({ id: z.string(), title: z.string(), progressSeconds: z.number().int().min(0).default(0) })).mutation(({ ctx, input }) => upsertWatchHistory(ctx.user.id, input, input.progressSeconds)),
  }),
});

export type AppRouter = typeof appRouter;
