import { describe, expect, it } from "vitest";
import { makeMovieFrSign, normalizeMovies, decryptMovieFrResponse } from "./moviefr";

describe("MovieFR adapter", () => {
  it("creates the verified uppercase MD5 sign", () => {
    expect(makeMovieFrSign("1720000000000", "0000000000000000")).toBe("266CD9AB150F051FA963ABB84B6CBD0C");
  });

  it("normalizes API movie records for cards", () => {
    expect(normalizeMovies({ list: [{ vod_id: 7, vod_name: "فيلم تجريبي", vod_pic: "https://img.test/poster.jpg", vod_year: 2026, vod_class: "دراما" }] })).toEqual([
      { id: "7", title: "فيلم تجريبي", poster: "https://img.test/poster.jpg", year: "2026", genre: "دراما", raw: { vod_id: 7, vod_name: "فيلم تجريبي", vod_pic: "https://img.test/poster.jpg", vod_year: 2026, vod_class: "دراما" } },
    ]);
  });

  it("does not throw on a plain JSON fallback response", () => {
    expect(decryptMovieFrResponse('{"list":[]}')).toEqual({ list: [] });
  });
});
