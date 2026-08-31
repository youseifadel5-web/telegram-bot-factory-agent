export const movieConfig = {
  botDisplayName: "يوسف بوت",
  appDisplayName: "Movie VIP",
  apiBaseUrl: "https://freecinefr.t62nds.com",
  streamBaseUrl: "https://moviefr.v7z5v0.com",
  appId: "moviefr",
  packageName: "com.mfr.moviefr",
  version: "30003",
  channelCode: "moviefr_1005",
  userAgent: "okhttp/4.12.0",
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
