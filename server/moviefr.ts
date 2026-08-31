import crypto from "node:crypto";
import { movieConfig } from "@shared/movieConfig";

const SIGN_CONST = "47Q8tBqO4YqrMHf4";

type MovieFrResult = Record<string, unknown> | unknown[] | string | null;

export function makeMovieFrSign(curTime: string, deviceId: string) {
  return crypto.createHash("md5").update(`${SIGN_CONST}${deviceId}${curTime}`, "utf8").digest("hex").toUpperCase();
}

function decodeBase64(value: string) {
  return Buffer.from(value, "base64");
}

function tryUnpad(value: Buffer) {
  if (!value.length) return value;
  const n = value[value.length - 1];
  if (n < 1 || n > 16 || n > value.length) return value;
  for (let i = value.length - n; i < value.length; i += 1) if (value[i] !== n) return value;
  return value.subarray(0, value.length - n);
}

export function decryptMovieFrResponse(raw: string): MovieFrResult {
  try {
    if (raw.trim().startsWith("{") || raw.trim().startsWith("[")) return JSON.parse(raw) as MovieFrResult;
  } catch {
    // Continue with encrypted decoding.
  }
  const encoded = raw.startsWith(movieConfig.responsePrefix) ? raw.slice(movieConfig.responsePrefix.length) : raw;
  const bytes = decodeBase64(encoded);
  const candidates = ["0123456789123456", "0123456789ABCDEF", "0123456789abcdef", "5F50xTeaL75ULFuA", "7Ad7Ad7Ad7Ad7Ad7", "5454D9E9B20FA692"];
  for (const key of candidates) {
    for (const mode of ["aes-128-ecb", "aes-128-cbc"] as const) {
      try {
        const iv = mode.endsWith("cbc") ? Buffer.from("2015030120123456") : null;
        const decipher = crypto.createDecipheriv(mode, Buffer.from(key), iv);
        decipher.setAutoPadding(true);
        const plain = Buffer.concat([decipher.update(bytes), decipher.final()]).toString("utf8");
        const parsed = JSON.parse(plain) as MovieFrResult;
        if (parsed) return parsed;
      } catch {
        // Candidate keys are intentionally tried defensively until the API format is confirmed.
      }
    }
  }
  try { return JSON.parse(bytes.toString("utf8")) as MovieFrResult; } catch { return raw; }
}

function getApiToken() {
  // Kept as a runtime override for deployments where the upstream token rotates.
  // The app continues to work with the configured public headers when the upstream allows it.
  return process.env.MOVIEFR_TOKEN ?? "";
}

export async function movieFrRequest(endpoint: string, body: Record<string, string | number> = {}) {
  const curTime = Date.now().toString();
  const deviceId = "movievip-telegram";
  const headers: Record<string, string> = {
    "content-type": "application/x-www-form-urlencoded",
    "user-agent": movieConfig.userAgent,
    app_id: movieConfig.appId,
    package_name: movieConfig.packageName,
    version: movieConfig.version,
    sys_platform: "2",
    channel_code: movieConfig.channelCode,
    app_language: "ar",
    is_language: "ar",
    is_vvv: "1",
    is_display: "GMT+02:00",
    device_id: deviceId,
    androidid: deviceId,
    cur_time: curTime,
    sign: makeMovieFrSign(curTime, deviceId),
  };
  const token = getApiToken();
  if (token) headers.token = token;
  const response = await fetch(`${movieConfig.apiBaseUrl}${endpoint}`, {
    method: "POST",
    headers,
    body: new URLSearchParams(Object.entries(body).map(([key, value]) => [key, String(value)])),
    signal: AbortSignal.timeout(12_000),
  });
  if (!response.ok) throw new Error(`MovieFR upstream returned ${response.status}`);
  return decryptMovieFrResponse(await response.text());
}

export function normalizeMovies(payload: MovieFrResult) {
  const candidates = Array.isArray(payload) ? payload : (payload && typeof payload === "object" ? ((payload as Record<string, unknown>).data ?? (payload as Record<string, unknown>).list ?? []) : []);
  if (!Array.isArray(candidates)) return [];
  return candidates.map((item, index) => {
    const movie = (item && typeof item === "object" ? item : {}) as Record<string, unknown>;
    return {
      id: String(movie.vod_id ?? movie.id ?? index),
      title: String(movie.vod_name ?? movie.name ?? "بدون عنوان"),
      poster: String(movie.vod_pic ?? movie.pic ?? ""),
      year: String(movie.vod_year ?? movie.year ?? ""),
      genre: String(movie.vod_class ?? movie.type_name ?? ""),
      raw: movie,
    };
  });
}

export function stripCandidatePadding(value: Buffer) { return tryUnpad(value); }
