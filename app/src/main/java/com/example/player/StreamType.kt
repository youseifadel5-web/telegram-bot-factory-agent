package com.example.player

enum class StreamType(val displayName: String) {
    HLS("HLS / M3U8"),
    DASH("DASH / MPD"),
    RTSP("RTSP Stream"),
    PROGRESSIVE("Direct Video"),
    WEB_EMBED("Web / HTML5"),
    UNKNOWN("Auto Detect")
}
