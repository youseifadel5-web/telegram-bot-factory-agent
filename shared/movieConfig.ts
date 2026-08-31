export const movieConfig = {
  apiBaseUrl: "https://freecinefr.t62nds.com",
  streamBaseUrl: "https://moviefr.v7z5v0.com",
  appId: "moviefr",
  packageName: "com.mfr.moviefr",
  version: "30003",
  channelCode: "moviefr_1005",
  userAgent: "okhttp/4.12.0",
  // Upstream token supplied in the authorized MovieFR API report. Rotate here if the upstream changes it.
  upstreamToken: "gAAAAABqlA22u4cXwL3INxXbj0RXBFIlPyNWvCs0qdcg7HY3QIP73TtU6reGoLGO64OfxJkaEyVDJa8D4u35CrP8M3xAeKddNiF7QtWdsC4IcRLiFMNtnqQaiklaBqnrYtW0bDJLtQI3O7xy9Rd2HInyK--4eQ5G3XtzqLQJSZuI_r3yuh_5NG6UdcZ_wZY657MKIQfWBHQ48HdEa43piNlHHMufvIF6mXPqCZHyNjeRCU0YScreU4LgMNEYbAyUkVgROrNxL8eu",
  responsePrefix: "SHOK5119",
  endpoints: {
    info: "/api/vod/info_new",
    search: "/api/search/result",
    suggest: "/api/search/suggest",
    hotSearch: "/api/search/hot_search",
    recommend: "/api/search/recommend",
    screen: "/api/search/screen",
    types: "/api/type/get_list",
    channels: "/api/channel/get_list",
    channelInfo: "/api/channel/get_info",
    topics: "/api/topic/list",
    topicVod: "/api/topic/vod_list",
    barrage: "/api/barrage/get_list",
    discuss: "/api/discuss/get_list_new",
  },
} as const;

export type MovieEndpoint = keyof typeof movieConfig.endpoints;
