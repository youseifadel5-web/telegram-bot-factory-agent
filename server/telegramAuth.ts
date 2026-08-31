import crypto from "node:crypto";

export function validateTelegramInitData(initData: string, maxAgeSeconds = 86_400) {
  const botToken = process.env.BOT_TOKEN;
  if (!botToken || !initData) return { valid: false as const, user: null };
  const params = new URLSearchParams(initData);
  const receivedHash = params.get("hash");
  const authDate = Number(params.get("auth_date") ?? 0);
  if (!receivedHash || !authDate || Math.floor(Date.now() / 1000) - authDate > maxAgeSeconds) return { valid: false as const, user: null };
  params.delete("hash");
  const dataCheckString = Array.from(params.entries()).sort(([a], [b]) => a.localeCompare(b)).map(([key, value]) => `${key}=${value}`).join("\n");
  const secretKey = crypto.createHmac("sha256", "WebAppData").update(botToken).digest();
  const expectedHash = crypto.createHmac("sha256", secretKey).update(dataCheckString).digest("hex");
  const valid = receivedHash.length === expectedHash.length && crypto.timingSafeEqual(Buffer.from(receivedHash), Buffer.from(expectedHash));
  let user: Record<string, unknown> | null = null;
  try { user = params.get("user") ? JSON.parse(params.get("user")!) : null; } catch { user = null; }
  return { valid, user };
}
