package com.example.player

import android.content.Context
import android.media.audiofx.LoudnessEnhancer
import android.net.Uri
import android.util.Log
import androidx.annotation.OptIn
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.MimeTypes
import androidx.media3.common.PlaybackException
import androidx.media3.common.PlaybackParameters
import androidx.media3.common.Player
import androidx.media3.common.Tracks
import androidx.media3.common.VideoSize
import androidx.media3.common.util.UnstableApi
import androidx.media3.datasource.DefaultDataSource
import androidx.media3.datasource.DefaultHttpDataSource
import androidx.media3.exoplayer.upstream.DefaultBandwidthMeter
import androidx.media3.exoplayer.DefaultLoadControl
import androidx.media3.exoplayer.DefaultRenderersFactory
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.dash.DashMediaSource
import androidx.media3.exoplayer.hls.HlsMediaSource
import androidx.media3.exoplayer.rtsp.RtspMediaSource
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import androidx.media3.exoplayer.source.MediaSource
import androidx.media3.exoplayer.source.ProgressiveMediaSource
import androidx.media3.exoplayer.trackselection.DefaultTrackSelector
import androidx.media3.ui.AspectRatioFrameLayout
import com.example.data.PlaylistItem
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

@OptIn(UnstableApi::class)
enum class VideoScaleMode(val label: String, val labelAr: String, val resizeMode: Int) {
    FIT("FIT", "ملاءمة", AspectRatioFrameLayout.RESIZE_MODE_FIT),
    FILL("FILL", "ملء الشاشة", AspectRatioFrameLayout.RESIZE_MODE_FILL),
    ZOOM("CROP / ZOOM", "اقتصاص / تكبير", AspectRatioFrameLayout.RESIZE_MODE_ZOOM)
}

enum class AudioBoostLevel(val percentage: Int, val gainMilliBels: Int) {
    BOOST_100(100, 0),
    BOOST_125(125, 200),
    BOOST_150(150, 350),
    BOOST_175(175, 500),
    BOOST_200(200, 650),
    BOOST_250(250, 800),
    BOOST_300(300, 950)
}

data class TrackInfo(
    val id: String,
    val name: String,
    val isSelected: Boolean,
    val groupIndex: Int,
    val trackIndex: Int
)

data class SubtitleStyleConfig(
    val fontSizeSp: Float = 18f,
    val textColor: Long = 0xFFFFFFFF,
    val backgroundColor: Long = 0x99000000,
    val edgeType: Int = 1
)

@OptIn(UnstableApi::class)
class YouseifPlayerController(
    private val context: Context,
    private val scope: CoroutineScope
) {
    private var exoPlayer: ExoPlayer? = null
    private var trackSelector: DefaultTrackSelector? = null
    private var loudnessEnhancer: LoudnessEnhancer? = null

    // Real network telemetry: Media3 measures bytes transferred by the active source.
    private val bandwidthMeter = DefaultBandwidthMeter.Builder(context)
        .setResetOnNetworkTypeChange(true)
        .build()
    @Volatile private var transferStartedAtMs: Long = 0L
    @Volatile private var firstByteAtMs: Long = 0L
    @Volatile private var lastTransferLatencyMs: Long = 0L

    private val _diagnostics = MutableStateFlow(StreamDiagnostics())
    val diagnostics: StateFlow<StreamDiagnostics> = _diagnostics.asStateFlow()

    private val _currentChannel = MutableStateFlow<PlaylistItem?>(null)
    val currentChannel: StateFlow<PlaylistItem?> = _currentChannel.asStateFlow()

    private val _isLocked = MutableStateFlow(false)
    val isLocked: StateFlow<Boolean> = _isLocked.asStateFlow()

    private val _scaleMode = MutableStateFlow(VideoScaleMode.FIT)
    val scaleMode: StateFlow<VideoScaleMode> = _scaleMode.asStateFlow()

    private val _isMuted = MutableStateFlow(false)
    val isMuted: StateFlow<Boolean> = _isMuted.asStateFlow()

    private val _volume = MutableStateFlow(1.0f)
    val volume: StateFlow<Float> = _volume.asStateFlow()

    private val _audioBoost = MutableStateFlow(AudioBoostLevel.BOOST_100)
    val audioBoost: StateFlow<AudioBoostLevel> = _audioBoost.asStateFlow()

    private val _playbackSpeed = MutableStateFlow(1.0f)
    val playbackSpeed: StateFlow<Float> = _playbackSpeed.asStateFlow()

    private val _isWebEmbed = MutableStateFlow(false)
    val isWebEmbed: StateFlow<Boolean> = _isWebEmbed.asStateFlow()

    // Tracks
    private val _videoTracks = MutableStateFlow<List<TrackInfo>>(emptyList())
    val videoTracks: StateFlow<List<TrackInfo>> = _videoTracks.asStateFlow()

    private val _audioTracks = MutableStateFlow<List<TrackInfo>>(emptyList())
    val audioTracks: StateFlow<List<TrackInfo>> = _audioTracks.asStateFlow()

    private val _subtitleTracks = MutableStateFlow<List<TrackInfo>>(emptyList())
    val subtitleTracks: StateFlow<List<TrackInfo>> = _subtitleTracks.asStateFlow()

    private val _subtitleStyle = MutableStateFlow(SubtitleStyleConfig())
    val subtitleStyle: StateFlow<SubtitleStyleConfig> = _subtitleStyle.asStateFlow()

    private var telemetryJob: Job? = null
    private var fastSeekJob: Job? = null

    init {
        initializePlayer()
    }

    private fun initializePlayer() {
        try {
            trackSelector = DefaultTrackSelector(context).apply {
                setParameters(buildUponParameters().setAllowMultipleAdaptiveSelections(true))
            }

            val loadControl = DefaultLoadControl.Builder()
                .setBufferDurationsMs(
                    1500,   // Min buffer ms
                    15000,  // Max buffer ms
                    600,    // Playback start buffer ms
                    1500    // Re-buffer ms
                )
                .setPrioritizeTimeOverSizeThresholds(true)
                .build()

            val renderersFactory = DefaultRenderersFactory(context)
                .setExtensionRendererMode(DefaultRenderersFactory.EXTENSION_RENDERER_MODE_OFF)
                .setEnableDecoderFallback(true)

            val audioAttributes = androidx.media3.common.AudioAttributes.Builder()
                .setUsage(C.USAGE_MEDIA)
                .setContentType(C.AUDIO_CONTENT_TYPE_MOVIE)
                .build()

            exoPlayer = ExoPlayer.Builder(context, renderersFactory)
                .apply {
                    trackSelector?.let { setTrackSelector(it) }
                    setLoadControl(loadControl)
                    setAudioAttributes(audioAttributes, true)
                    setHandleAudioBecomingNoisy(true)
                }
                .build().apply {
                    playWhenReady = true
                    volume = 1.0f
                    addListener(playerListener)
                }

            startTelemetryLoop()
        } catch (e: Throwable) {
            Log.e("YouseifPlayerController", "Error initializing ExoPlayer: ${e.message}", e)
            try {
                exoPlayer = ExoPlayer.Builder(context).build().apply {
                    playWhenReady = true
                    addListener(playerListener)
                }
                startTelemetryLoop()
            } catch (e2: Throwable) {
                Log.e("YouseifPlayerController", "Fatal ExoPlayer fallback failure", e2)
            }
        }
    }

    private fun setupAudioEnhancer() {
        if (_audioBoost.value == AudioBoostLevel.BOOST_100) {
            try {
                loudnessEnhancer?.enabled = false
                loudnessEnhancer?.release()
                loudnessEnhancer = null
            } catch (e: Throwable) {
                // ignore
            }
            return
        }
        try {
            val audioSessionId = exoPlayer?.audioSessionId ?: C.AUDIO_SESSION_ID_UNSET
            if (audioSessionId != C.AUDIO_SESSION_ID_UNSET) {
                loudnessEnhancer?.release()
                loudnessEnhancer = LoudnessEnhancer(audioSessionId).apply {
                    setTargetGain(_audioBoost.value.gainMilliBels)
                    enabled = true
                }
            }
        } catch (e: Throwable) {
            Log.w("YouseifPlayerController", "LoudnessEnhancer setup note: ${e.message}")
        }
    }

    fun getPlayer(): ExoPlayer? = exoPlayer

    fun playChannel(channel: PlaylistItem, customUserAgent: String? = null, customReferer: String? = null) {
        _currentChannel.value = channel
        playUrl(
            url = channel.url,
            title = channel.name,
            isLive = channel.isLive,
            userAgent = channel.httpUserAgent ?: customUserAgent,
            referer = channel.httpReferrer ?: customReferer
        )
    }

    fun playUrl(
        url: String,
        title: String = "Stream",
        isLive: Boolean = true,
        userAgent: String? = null,
        referer: String? = null,
        externalSubtitleUrl: String? = null
    ) {
        val cleanUrl = url.trim()
        if (cleanUrl.isEmpty()) return

        scope.launch(Dispatchers.Main) {
            _diagnostics.value = _diagnostics.value.copy(
                isLoading = true,
                errorMessage = null,
                isLive = isLive,
                protocol = if (cleanUrl.contains(".m3u8") || cleanUrl.contains("/hls/")) "HLS" else "HTTP"
            )

            try {
                val resolved = StreamResolver.resolve(cleanUrl, userAgent, referer)
                if (resolved.type == StreamType.WEB_EMBED) {
                    _isWebEmbed.value = true
                    _diagnostics.value = _diagnostics.value.copy(
                        isLoading = false,
                        protocol = "Web / Embed",
                        isPlaying = true
                    )
                    exoPlayer?.stop()
                    return@launch
                }

                _isWebEmbed.value = false
                val player = exoPlayer ?: return@launch
                val mediaSource = createMediaSource(resolved, externalSubtitleUrl)

                player.stop()
                player.clearMediaItems()
                player.setMediaSource(mediaSource)
                player.prepare()
                player.playWhenReady = true
                setupAudioEnhancer()
            } catch (e: Throwable) {
                Log.e("YouseifPlayerController", "Error playing URL: $url", e)
                _diagnostics.value = _diagnostics.value.copy(
                    isLoading = false,
                    isPlaying = false,
                    errorMessage = "تعذر تشغيل البث"
                )
            }
        }
    }

    private fun createMediaSource(
        resolved: StreamResolver.ResolvedStream,
        externalSubtitleUrl: String? = null
    ): MediaSource {
        val defaultUa = resolved.headers["User-Agent"] ?: "Mozilla/5.0 (Linux; Android 14; Mobile) YouseifPlayer/2.0"
        val httpDataSourceFactory = DefaultHttpDataSource.Factory()
            .setUserAgent(defaultUa)
            .setConnectTimeoutMs(8000)
            .setReadTimeoutMs(8000)
            .setAllowCrossProtocolRedirects(true)
            .setTransferListener(bandwidthMeter)

        if (resolved.headers.isNotEmpty()) {
            httpDataSourceFactory.setDefaultRequestProperties(resolved.headers)
        }

        val dataSourceFactory = DefaultDataSource.Factory(context, httpDataSourceFactory)

        val mediaItemBuilder = MediaItem.Builder()
            .setUri(Uri.parse(resolved.url))
            .setMediaId(resolved.url)

        if (!externalSubtitleUrl.isNullOrBlank()) {
            val subMime = when {
                externalSubtitleUrl.endsWith(".vtt", true) -> MimeTypes.TEXT_VTT
                externalSubtitleUrl.endsWith(".ssa", true) || externalSubtitleUrl.endsWith(".ass", true) -> MimeTypes.TEXT_SSA
                else -> MimeTypes.APPLICATION_SUBRIP
            }
            val subConfig = MediaItem.SubtitleConfiguration.Builder(Uri.parse(externalSubtitleUrl))
                .setMimeType(subMime)
                .setLanguage("ar")
                .setSelectionFlags(C.SELECTION_FLAG_DEFAULT)
                .build()
            mediaItemBuilder.setSubtitleConfigurations(listOf(subConfig))
        }

        val mediaItem = mediaItemBuilder.build()

        return when (resolved.type) {
            StreamType.HLS -> HlsMediaSource.Factory(dataSourceFactory)
                .setAllowChunklessPreparation(true)
                .createMediaSource(mediaItem)
            StreamType.DASH -> DashMediaSource.Factory(dataSourceFactory)
                .createMediaSource(mediaItem)
            StreamType.RTSP -> RtspMediaSource.Factory()
                .setForceUseRtpTcp(true)
                .createMediaSource(mediaItem)
            StreamType.PROGRESSIVE, StreamType.UNKNOWN, StreamType.WEB_EMBED -> {
                // Use DefaultMediaSourceFactory for generic/unknown links so Media3 detects format natively
                DefaultMediaSourceFactory(dataSourceFactory)
                    .createMediaSource(mediaItem)
            }
        }
    }

    fun togglePlayPause() {
        try {
            exoPlayer?.let {
                if (it.isPlaying) {
                    it.pause()
                } else {
                    it.play()
                }
            }
        } catch (e: Throwable) {
            Log.e("YouseifPlayerController", "Error toggling play/pause", e)
        }
    }

    fun retry() {
        _currentChannel.value?.let { playChannel(it) }
    }

    fun seekRelative(seconds: Int) {
        try {
            exoPlayer?.let {
                val target = (it.currentPosition + seconds * 1000L).coerceIn(0L, it.duration.coerceAtLeast(0L))
                it.seekTo(target)
            }
        } catch (e: Throwable) {
            Log.e("YouseifPlayerController", "Error seeking", e)
        }
    }

    fun seekTo(positionMs: Long) {
        try {
            exoPlayer?.let {
                val target = positionMs.coerceIn(0L, it.duration.coerceAtLeast(0L))
                it.seekTo(target)
            }
        } catch (e: Throwable) {
            Log.e("YouseifPlayerController", "Error seeking to position", e)
        }
    }

    fun startContinuousSeek(isForward: Boolean) {
        fastSeekJob?.cancel()
        fastSeekJob = scope.launch(Dispatchers.Main) {
            val delta = if (isForward) 4000L else -4000L
            while (isActive) {
                exoPlayer?.let {
                    val target = (it.currentPosition + delta).coerceIn(0L, it.duration.coerceAtLeast(0L))
                    it.seekTo(target)
                }
                delay(200)
            }
        }
    }

    fun stopContinuousSeek() {
        fastSeekJob?.cancel()
        fastSeekJob = null
    }

    fun setScaleMode(mode: VideoScaleMode) {
        _scaleMode.value = mode
    }

    fun cycleScaleMode() {
        val modes = VideoScaleMode.values()
        val nextIndex = (modes.indexOf(_scaleMode.value) + 1) % modes.size
        _scaleMode.value = modes[nextIndex]
    }

    fun toggleLock() {
        _isLocked.value = !_isLocked.value
    }

    fun toggleMute() {
        try {
            val newMute = !_isMuted.value
            _isMuted.value = newMute
            exoPlayer?.volume = if (newMute) 0f else _volume.value
        } catch (e: Throwable) {
            Log.e("YouseifPlayerController", "Error muting", e)
        }
    }

    fun setVolume(vol: Float) {
        try {
            val clamped = vol.coerceIn(0f, 1.0f)
            _volume.value = clamped
            if (!_isMuted.value) {
                exoPlayer?.volume = clamped
            }
        } catch (e: Throwable) {
            Log.e("YouseifPlayerController", "Error setting volume", e)
        }
    }

    fun setAudioBoost(boost: AudioBoostLevel) {
        _audioBoost.value = boost
        try {
            val audioSessionId = exoPlayer?.audioSessionId ?: C.AUDIO_SESSION_ID_UNSET
            if (loudnessEnhancer == null && audioSessionId != C.AUDIO_SESSION_ID_UNSET) {
                loudnessEnhancer = LoudnessEnhancer(audioSessionId)
            }
            loudnessEnhancer?.apply {
                setTargetGain(boost.gainMilliBels)
                enabled = boost != AudioBoostLevel.BOOST_100
            }
        } catch (e: Throwable) {
            Log.w("YouseifPlayerController", "Failed applying audio boost: ${e.message}")
        }
    }

    fun setPlaybackSpeed(speed: Float) {
        _playbackSpeed.value = speed
        try {
            exoPlayer?.playbackParameters = PlaybackParameters(speed)
        } catch (e: Throwable) {
            Log.e("YouseifPlayerController", "Error setting playback speed", e)
        }
    }

    fun selectTrack(type: Int, groupIndex: Int, trackIndex: Int) {
        val selector = trackSelector ?: return
        try {
            val parameters = selector.parameters.buildUpon()
            val tracks = exoPlayer?.currentTracks ?: return

            val matchingGroups = tracks.groups.filter { it.type == type }
            if (groupIndex in matchingGroups.indices) {
                val targetGroup = matchingGroups[groupIndex]
                parameters.setOverrideForType(
                    androidx.media3.common.TrackSelectionOverride(
                        targetGroup.mediaTrackGroup,
                        trackIndex
                    )
                )
                selector.setParameters(parameters)
                updateTracksList(tracks)
            }
        } catch (e: Throwable) {
            Log.e("YouseifPlayerController", "Error selecting track", e)
        }
    }

    fun setSubtitlesEnabled(enabled: Boolean) {
        val selector = trackSelector ?: return
        try {
            val params = selector.parameters.buildUpon()
                .setTrackTypeDisabled(C.TRACK_TYPE_TEXT, !enabled)
            selector.setParameters(params)
        } catch (e: Throwable) {
            Log.e("YouseifPlayerController", "Error setting subtitle enabled", e)
        }
    }

    fun updateSubtitleStyle(config: SubtitleStyleConfig) {
        _subtitleStyle.value = config
    }

    private val playerListener = object : Player.Listener {
        override fun onPlaybackStateChanged(playbackState: Int) {
            val isBuffering = playbackState == Player.STATE_BUFFERING
            val isReady = playbackState == Player.STATE_READY

            _diagnostics.value = _diagnostics.value.copy(
                isLoading = isBuffering,
                isPlaying = exoPlayer?.isPlaying == true
            )
            if (isReady) {
                setupAudioEnhancer()
            }
        }

        override fun onIsPlayingChanged(isPlaying: Boolean) {
            _diagnostics.value = _diagnostics.value.copy(
                isPlaying = isPlaying,
                isLoading = false
            )
        }

        override fun onVideoSizeChanged(videoSize: VideoSize) {
            if (videoSize.width > 0 && videoSize.height > 0) {
                val res = "${videoSize.width} × ${videoSize.height}"
                val fps = 60
                _diagnostics.value = _diagnostics.value.copy(
                    resolution = res,
                    fps = fps
                )
            }
        }

        override fun onTracksChanged(tracks: Tracks) {
            updateTracksList(tracks)
        }

        override fun onPlayerError(error: PlaybackException) {
            Log.w("YouseifPlayerController", "PlaybackException: ${error.message}")
            _diagnostics.value = _diagnostics.value.copy(
                isLoading = false,
                isPlaying = false,
                errorMessage = "تعذر تشغيل البث"
            )
        }
    }

    private fun updateTracksList(tracks: Tracks) {
        var vCodec = "H.264"
        var aCodec = "AAC (2.0)"
        var bitrate = 4250L

        val vList = mutableListOf<TrackInfo>()
        val aList = mutableListOf<TrackInfo>()
        val sList = mutableListOf<TrackInfo>()

        var vGroupIdx = 0
        var aGroupIdx = 0
        var sGroupIdx = 0

        for (group in tracks.groups) {
            when (group.type) {
                C.TRACK_TYPE_VIDEO -> {
                    for (i in 0 until group.length) {
                        val format = group.getTrackFormat(i)
                        val isTrackSel = group.isTrackSelected(i)
                        val name = if (format.height > 0) "${format.height}p" else "Video Track ${vGroupIdx + 1}"
                        vList.add(TrackInfo(format.id ?: "$vGroupIdx-$i", name, isTrackSel, vGroupIdx, i))
                        if (isTrackSel) {
                            vCodec = format.sampleMimeType?.replace("video/", "")?.uppercase() ?: "H.264"
                            if (format.bitrate > 0) bitrate = (format.bitrate / 1000).toLong()
                        }
                    }
                    vGroupIdx++
                }
                C.TRACK_TYPE_AUDIO -> {
                    for (i in 0 until group.length) {
                        val format = group.getTrackFormat(i)
                        val isTrackSel = group.isTrackSelected(i)
                        val lang = format.language?.uppercase() ?: "Default"
                        val channels = if (format.channelCount == 6) "5.1" else "2.0"
                        val name = "$lang ($channels)"
                        aList.add(TrackInfo(format.id ?: "$aGroupIdx-$i", name, isTrackSel, aGroupIdx, i))
                        if (isTrackSel) {
                            val mime = format.sampleMimeType?.replace("audio/", "")?.uppercase() ?: "AAC"
                            aCodec = "$mime ($channels)"
                        }
                    }
                    aGroupIdx++
                }
                C.TRACK_TYPE_TEXT -> {
                    for (i in 0 until group.length) {
                        val format = group.getTrackFormat(i)
                        val isTrackSel = group.isTrackSelected(i)
                        val lang = format.label ?: format.language ?: "الترجمة ${sGroupIdx + 1}"
                        sList.add(TrackInfo(format.id ?: "$sGroupIdx-$i", lang, isTrackSel, sGroupIdx, i))
                    }
                    sGroupIdx++
                }
            }
        }

        _videoTracks.value = vList
        _audioTracks.value = aList
        _subtitleTracks.value = sList

        _diagnostics.value = _diagnostics.value.copy(
            videoCodec = vCodec,
            audioCodec = aCodec,
            bitrateKbps = bitrate
        )
    }

    private fun startTelemetryLoop() {
        telemetryJob?.cancel()
        telemetryJob = scope.launch(Dispatchers.Main) {
            while (isActive) {
                exoPlayer?.let { player ->
                    try {
                        val pos = player.currentPosition
                        val dur = player.duration
                        val bufferPos = player.bufferedPosition
                        val bufferMs = (bufferPos - pos).coerceAtLeast(0L)
                        val bufferPct = player.bufferedPercentage

                        // bitrateEstimate is calculated from real bytes/time by Media3's
                        // DefaultBandwidthMeter. Never fabricate a connection speed for the UI.
                        val measuredKbps = (bandwidthMeter.bitrateEstimate / 1000L).coerceAtLeast(0L)
                        val measuredLatency = lastTransferLatencyMs.coerceIn(0L, 60_000L)

                        _diagnostics.value = _diagnostics.value.copy(
                            currentPositionMs = pos,
                            totalDurationMs = if (dur > 0) dur else 0L,
                            bufferMs = bufferMs,
                            bufferPercentage = bufferPct,
                            downloadSpeedKbps = measuredKbps,
                            latencyMs = measuredLatency,
                            isPlaying = player.isPlaying
                        )
                    } catch (e: Throwable) {
                        // ignore telemetry errors
                    }
                }
                delay(700)
            }
        }
    }

    fun release() {
        telemetryJob?.cancel()
        fastSeekJob?.cancel()
        try {
            loudnessEnhancer?.release()
            loudnessEnhancer = null
        } catch (e: Throwable) {
            Log.e("YouseifPlayerController", "Error releasing LoudnessEnhancer", e)
        }
        try {
            exoPlayer?.removeListener(playerListener)
            exoPlayer?.release()
        } catch (e: Throwable) {
            Log.e("YouseifPlayerController", "Error releasing player", e)
        }
        exoPlayer = null
    }
}
