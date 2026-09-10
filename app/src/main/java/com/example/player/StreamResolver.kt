package com.example.player

import android.net.Uri
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

object StreamResolver {

    data class ResolvedStream(
        val url: String,
        val type: StreamType,
        val contentType: String? = null,
        val headers: Map<String, String> = emptyMap()
    )

    suspend fun resolve(
        rawUrl: String,
        customUserAgent: String? = null,
        customReferer: String? = null
    ): ResolvedStream = withContext(Dispatchers.Default) {
        var trimmed = rawUrl.trim()
        if (trimmed.isEmpty()) {
            return@withContext ResolvedStream(trimmed, StreamType.UNKNOWN)
        }

        // Direct Pixeldrain URL translation: /u/ID -> /api/file/ID
        if (trimmed.contains("pixeldrain.com/u/", ignoreCase = true)) {
            val id = trimmed.substringAfter("pixeldrain.com/u/").substringBefore("?").substringBefore("/")
            if (id.isNotBlank()) {
                trimmed = "https://pixeldrain.com/api/file/$id"
            }
        }

        val headers = mutableMapOf<String, String>()
        if (!customUserAgent.isNullOrBlank()) {
            headers["User-Agent"] = customUserAgent
        } else {
            headers["User-Agent"] = "Mozilla/5.0 (Linux; Android 14; Mobile) AppleWebKit/537.36 YouseifPlayer/2.0"
        }
        if (!customReferer.isNullOrBlank()) {
            headers["Referer"] = customReferer
        }

        // Scheme check for RTSP / RTMP
        if (trimmed.startsWith("rtsp://", ignoreCase = true) || trimmed.startsWith("rtsps://", ignoreCase = true)) {
            return@withContext ResolvedStream(trimmed, StreamType.RTSP, "application/x-rtsp", headers)
        }

        // Pixeldrain direct file API
        if (trimmed.contains("pixeldrain.com/api/file/", ignoreCase = true)) {
            return@withContext ResolvedStream(trimmed, StreamType.PROGRESSIVE, "video/mp4", headers)
        }

        val uri = try { Uri.parse(trimmed) } catch (e: Exception) { null }
        val path = uri?.path?.lowercase() ?: ""

        // Standard extension and keyword detection without network blocking delays
        if (path.endsWith(".m3u8") || trimmed.contains(".m3u8", ignoreCase = true) || trimmed.contains("/hls/", ignoreCase = true)) {
            return@withContext ResolvedStream(trimmed, StreamType.HLS, "application/vnd.apple.mpegurl", headers)
        }
        if (path.endsWith(".mpd") || trimmed.contains(".mpd", ignoreCase = true) || trimmed.contains("/dash/", ignoreCase = true)) {
            return@withContext ResolvedStream(trimmed, StreamType.DASH, "application/dash+xml", headers)
        }
        if (path.endsWith(".mp4") || path.endsWith(".mkv") || path.endsWith(".ts") ||
            path.endsWith(".webm") || path.endsWith(".avi") || path.endsWith(".mov") || path.endsWith(".flv")) {
            return@withContext ResolvedStream(trimmed, StreamType.PROGRESSIVE, "video/mp4", headers)
        }

        // Web embed detection for full html pages
        if (path.endsWith(".html") || path.endsWith(".htm") || (trimmed.contains("youtube.com/embed", ignoreCase = true))) {
            return@withContext ResolvedStream(trimmed, StreamType.WEB_EMBED, "text/html", headers)
        }

        // Default: For any media URL even without extension or with query params, Media3 handles progressive & HLS
        ResolvedStream(trimmed, StreamType.PROGRESSIVE, null, headers)
    }
}
