package com.example.player

data class StreamDiagnostics(
    val isPlaying: Boolean = false,
    val isLoading: Boolean = false,
    val resolution: String = "1920x1080",
    val fps: Int = 60,
    val videoCodec: String = "H.264 / AVC",
    val audioCodec: String = "AAC Stereo (48kHz)",
    val bitrateKbps: Long = 4500L,
    val bufferMs: Long = 3200L,
    val bufferPercentage: Int = 85,
    val protocol: String = "HTTPS (HLS)",
    val latencyMs: Long = 0L,
    val downloadSpeedKbps: Long = 0L,
    val droppedFrames: Int = 0,
    val currentPositionMs: Long = 0L,
    val totalDurationMs: Long = 0L,
    val isLive: Boolean = true,
    val errorMessage: String? = null
)
