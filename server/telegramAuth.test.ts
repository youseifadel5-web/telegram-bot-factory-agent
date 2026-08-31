import { describe, expect, it } from "vitest";
import { validateTelegramInitData } from "./telegramAuth";

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
});
