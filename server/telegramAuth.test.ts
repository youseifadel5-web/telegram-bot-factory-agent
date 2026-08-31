import { describe, expect, it } from "vitest";
import { validateTelegramInitData } from "./telegramAuth";
import { validateTelegramConfig } from "./telegramBot";

describe("Telegram Web App auth", () => {
  it("rejects missing credentials without throwing", () => {
    const previous = process.env.BOT_TOKEN;
    delete process.env.BOT_TOKEN;
    expect(validateTelegramInitData("")).toEqual({ valid: false, user: null });
    if (previous) process.env.BOT_TOKEN = previous;
  });

  it("rejects malformed initData", () => {
    process.env.BOT_TOKEN = "test-token";
    expect(validateTelegramInitData("auth_date=not-a-date&hash=bad")).toEqual({ valid: false, user: null });
  });

  it("reports missing Telegram configuration by key only", () => {
    const result = validateTelegramConfig({});
    expect(result.valid).toBe(false);
    expect(result.missing).toEqual(["ADMIN_ID", "API_ID", "API_HASH", "BOT_TOKEN"]);
    expect(JSON.stringify(result)).not.toContain("test-token");
  });

  it("rejects malformed Telegram identifiers", () => {
    const result = validateTelegramConfig({ ADMIN_ID: "abc", API_ID: "x", API_HASH: "short", BOT_TOKEN: "bad" });
    expect(result.valid).toBe(false);
    expect(result.malformed).toEqual(["ADMIN_ID", "API_ID", "API_HASH", "BOT_TOKEN"]);
  });
});
