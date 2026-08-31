import { Bot, InlineKeyboard, InputFile } from "grammy";
import { movieConfig } from "@shared/movieConfig";
import { movieFrRequest, normalizeMovies } from "./moviefr";

const miniAppUrl = process.env.MINI_APP_URL ?? "";
let bot: Bot | null = null;

export function validateTelegramConfig(env: NodeJS.ProcessEnv = process.env) {
  const missing = ["ADMIN_ID", "API_ID", "API_HASH", "BOT_TOKEN"].filter((key) => !env[key]?.trim());
  const malformed = [] as string[];
  if (env.ADMIN_ID && !/^\\d+$/.test(env.ADMIN_ID)) malformed.push("ADMIN_ID");
  if (env.API_ID && !/^\\d+$/.test(env.API_ID)) malformed.push("API_ID");
  if (env.API_HASH && env.API_HASH.length < 16) malformed.push("API_HASH");
  if (env.BOT_TOKEN && !/^\\d+:[A-Za-z0-9_-]{20,}$/.test(env.BOT_TOKEN)) malformed.push("BOT_TOKEN");
  return { valid: missing.length === 0 && malformed.length === 0, missing, malformed };
}

function isAdmin(userId: number) {
  return String(userId) === String(process.env.ADMIN_ID ?? "");
}

function appKeyboard() {
  const keyboard = new InlineKeyboard();
  if (miniAppUrl) keyboard.webApp("فتح Movie VIP", miniAppUrl);
  return keyboard.url("قناة التحديثات", "https://t.me/movievip");
}

function movieKeyboard(id: string) {
  const keyboard = new InlineKeyboard().text("التفاصيل والجودات", `movie:${id}`);
  if (miniAppUrl) keyboard.webApp("فتح داخل التطبيق", `${miniAppUrl}?movie=${encodeURIComponent(id)}`);
  return keyboard;
}

export function createTelegramBot() {
  const config = validateTelegramConfig();
  if (!config.valid) {
    console.warn(`[Telegram] Bot disabled; configuration issues: ${[...config.missing, ...config.malformed].join(", ") || "unknown"}`);
    return null;
  }
  const token = process.env.BOT_TOKEN!;
  bot = new Bot(token);
  bot.command("start", async (ctx) => {
    await ctx.reply("أهلاً بك في Movie VIP\nابحث عن أي فيلم أو مسلسل، وسأعرض لك الصورة والتفاصيل والجودات المتاحة.", { reply_markup: appKeyboard() });
  });
  bot.command("help", (ctx) => ctx.reply("اكتب اسم الفيلم مباشرة، أو استخدم /search ثم كلمة البحث.\nاستخدم /app لفتح الواجهة الكاملة."));
  bot.command("app", (ctx) => ctx.reply("افتح Movie VIP من هنا:", { reply_markup: appKeyboard() }));
  bot.command("admin", async (ctx) => {
    if (!ctx.from || !isAdmin(ctx.from.id)) return ctx.reply("هذا الأمر مخصص للإدارة فقط.");
    await ctx.reply(`لوحة الإدارة جاهزة. المستخدمون: ${ctx.chat.id}`);
  });
  bot.command("search", async (ctx) => {
    const query = ctx.match.trim();
    if (!query) return ctx.reply("اكتب اسم الفيلم بعد الأمر، مثال: /search Interstellar");
    await sendSearch(ctx, query);
  });
  bot.on("message:text", async (ctx) => {
    const query = ctx.message.text.trim();
    if (query.startsWith("/")) return;
    await sendSearch(ctx, query);
  });
  bot.callbackQuery(/^movie:(.+)$/, async (ctx) => {
    await ctx.answerCallbackQuery();
    const id = ctx.match[1];
    try {
      const payload = await movieFrRequest(movieConfig.endpoints.info, { vod_id: id });
      const item = payload && typeof payload === "object" ? payload as Record<string, unknown> : {};
      const title = String(item.vod_name ?? item.name ?? "تفاصيل الفيلم");
      const year = String(item.vod_year ?? item.year ?? "");
      const desc = String(item.vod_blurb ?? item.vod_content ?? item.content ?? "");
      await ctx.reply(`🎬 ${title}\n${year}\n\n${desc.slice(0, 900) || "التفاصيل متاحة داخل الواجهة."}`, { reply_markup: appKeyboard() });
    } catch {
      await ctx.reply("تعذر جلب التفاصيل الآن. جرّب مرة أخرى بعد قليل.");
    }
  });
  return bot;
}

async function sendSearch(ctx: any, query: string) {
  try {
    const payload = await movieFrRequest(movieConfig.endpoints.search, { kw: query, pn: 1 });
    const results = normalizeMovies(payload).slice(0, 6);
    if (!results.length) return ctx.reply(`لم أجد نتائج لـ «${query}». جرّب اسماً آخر.`);
    await ctx.reply(`نتائج البحث عن «${query}» — ${results.length} أفلام`, { reply_markup: appKeyboard() });
    for (const movie of results) {
      const caption = `🎬 ${movie.title}\n${movie.year}${movie.genre ? ` · ${movie.genre}` : ""}`;
      if (movie.poster && movie.poster.startsWith("http")) {
        await ctx.replyWithPhoto(movie.poster, { caption, reply_markup: movieKeyboard(movie.id) });
      } else {
        await ctx.reply(caption, { reply_markup: movieKeyboard(movie.id) });
      }
    }
  } catch {
    await ctx.reply("حدث خطأ مؤقت أثناء البحث. تأكد من اتصال الخادم وحاول مرة أخرى.");
  }
}

export async function startTelegramBot() {
  const instance = bot ?? createTelegramBot();
  if (!instance) return false;
  if (process.env.TELEGRAM_MODE === "polling") {
    await instance.start({ onStart: (info) => console.log(`[Telegram] @${info.username} polling started`) });
  }
  return true;
}

export function getTelegramBot() { return bot; }
