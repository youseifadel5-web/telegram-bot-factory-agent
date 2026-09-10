package com.example.ui.components

import android.annotation.SuppressLint
import android.app.Activity
import android.app.PictureInPictureParams
import android.content.Context
import android.os.Build
import android.util.Rational
import android.view.ViewGroup
import android.webkit.WebChromeClient
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.annotation.OptIn
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.scaleOut
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.AspectRatio
import androidx.compose.material.icons.filled.Cast
import androidx.compose.material.icons.filled.ClosedCaption
import androidx.compose.material.icons.filled.Forward10
import androidx.compose.material.icons.filled.Fullscreen
import androidx.compose.material.icons.filled.FullscreenExit
import androidx.compose.material.icons.filled.GraphicEq
import androidx.compose.material.icons.filled.HighQuality
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.LockOpen
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PictureInPictureAlt
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.PlaylistPlay
import androidx.compose.material.icons.filled.Replay
import androidx.compose.material.icons.filled.Replay10
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.SkipNext
import androidx.compose.material.icons.filled.SkipPrevious
import androidx.compose.material.icons.filled.Speed
import androidx.compose.material.icons.filled.VolumeOff
import androidx.compose.material.icons.filled.VolumeUp
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.media3.common.C
import androidx.media3.common.util.UnstableApi
import androidx.media3.ui.CaptionStyleCompat
import androidx.media3.ui.PlayerView
import com.example.player.AudioBoostLevel
import com.example.player.SubtitleStyleConfig
import com.example.player.VideoScaleMode
import com.example.player.YouseifPlayerController
import com.example.ui.theme.AmoledBlack
import com.example.ui.theme.CrimsonBorder
import com.example.ui.theme.DarkCardBg
import com.example.ui.theme.DarkSurface
import com.example.ui.theme.DarkSurfaceVariant
import com.example.ui.theme.LiveRed
import com.example.ui.theme.NeonRed
import com.example.ui.theme.NeonRedContainer
import com.example.ui.theme.NeonRedGlow
import com.example.ui.theme.TechCyan
import com.example.ui.theme.TextMuted
import com.example.ui.theme.TextPrimary
import com.example.ui.theme.TextSecondary
import kotlinx.coroutines.delay

@SuppressLint("SetJavaScriptEnabled")
@OptIn(UnstableApi::class)
@Composable
fun VideoPlayerView(
    controller: YouseifPlayerController,
    modifier: Modifier = Modifier,
    isFullscreen: Boolean = false,
    onToggleFullscreen: () -> Unit = {},
    onPreviousChannel: () -> Unit = {},
    onNextChannel: () -> Unit = {},
    onOpenPlaylist: () -> Unit = {},
    onOpenSettings: () -> Unit = {}
) {
    val context = LocalContext.current
    val activity = context as? Activity
    val diagnostics by controller.diagnostics.collectAsState()
    val currentChannel by controller.currentChannel.collectAsState()
    val isLocked by controller.isLocked.collectAsState()
    val scaleMode by controller.scaleMode.collectAsState()
    val isMuted by controller.isMuted.collectAsState()
    val volume by controller.volume.collectAsState()
    val audioBoost by controller.audioBoost.collectAsState()
    val playbackSpeed by controller.playbackSpeed.collectAsState()
    val isWebEmbed by controller.isWebEmbed.collectAsState()
    val videoTracks by controller.videoTracks.collectAsState()
    val audioTracks by controller.audioTracks.collectAsState()
    val subtitleTracks by controller.subtitleTracks.collectAsState()
    val subtitleStyle by controller.subtitleStyle.collectAsState()

    var showControls by remember { mutableStateOf(true) }
    var showQualityDialog by remember { mutableStateOf(false) }
    var showAudioDialog by remember { mutableStateOf(false) }
    var showSubtitleDialog by remember { mutableStateOf(false) }
    var showSpeedDialog by remember { mutableStateOf(false) }
    var showMoreMenu by remember { mutableStateOf(false) }

    // Gesture feedback indicators
    var gestureOverlayText by remember { mutableStateOf<String?>(null) }
    var gestureOverlayIcon by remember { mutableStateOf<String?>(null) }
    var doubleTapFeedback by remember { mutableStateOf<String?>(null) }
    var isSeekingForwardContinuous by remember { mutableStateOf(false) }
    var isSeekingBackwardContinuous by remember { mutableStateOf(false) }

    // Brightness state (0..1)
    var currentBrightness by remember {
        mutableFloatStateOf(activity?.window?.attributes?.screenBrightness?.takeIf { it in 0f..1f } ?: 0.5f)
    }

    // Auto-hide controls after 4.5 seconds
    LaunchedEffect(showControls, diagnostics.isPlaying, isLocked) {
        if (showControls && diagnostics.isPlaying && !isLocked) {
            delay(4500)
            showControls = false
        }
    }

    // Clear gesture feedback after delay
    LaunchedEffect(gestureOverlayText) {
        if (gestureOverlayText != null) {
            delay(1200)
            gestureOverlayText = null
            gestureOverlayIcon = null
        }
    }

    LaunchedEffect(doubleTapFeedback) {
        if (doubleTapFeedback != null) {
            delay(700)
            doubleTapFeedback = null
        }
    }

    Box(
        modifier = modifier
            .background(AmoledBlack)
            .border(
                width = if (isFullscreen) 0.dp else 1.dp,
                color = if (isFullscreen) Color.Transparent else CrimsonBorder,
                shape = if (isFullscreen) RoundedCornerShape(0.dp) else RoundedCornerShape(12.dp)
            )
            .clip(if (isFullscreen) RoundedCornerShape(0.dp) else RoundedCornerShape(12.dp))
    ) {
        if (isWebEmbed) {
            // Web / HTML5 Embed Fallback
            AndroidView(
                factory = { ctx ->
                    WebView(ctx).apply {
                        layoutParams = ViewGroup.LayoutParams(
                            ViewGroup.LayoutParams.MATCH_PARENT,
                            ViewGroup.LayoutParams.MATCH_PARENT
                        )
                        settings.javaScriptEnabled = true
                        settings.domStorageEnabled = true
                        settings.mediaPlaybackRequiresUserGesture = false
                        webViewClient = WebViewClient()
                        webChromeClient = WebChromeClient()
                        currentChannel?.url?.let { loadUrl(it) }
                    }
                },
                modifier = Modifier.fillMaxSize()
            )
        } else {
            // ExoPlayer View
            AndroidView(
                factory = { ctx ->
                    PlayerView(ctx).apply {
                        useController = false
                        resizeMode = scaleMode.resizeMode
                        player = controller.getPlayer()
                        keepScreenOn = true

                        subtitleView?.apply {
                            setStyle(
                                CaptionStyleCompat(
                                    subtitleStyle.textColor.toInt(),
                                    subtitleStyle.backgroundColor.toInt(),
                                    0x00000000,
                                    CaptionStyleCompat.EDGE_TYPE_OUTLINE,
                                    0xFF000000.toInt(),
                                    null
                                )
                            )
                            setFixedTextSize(android.util.TypedValue.COMPLEX_UNIT_SP, subtitleStyle.fontSizeSp)
                        }
                    }
                },
                update = { playerView ->
                    if (playerView.player != controller.getPlayer()) {
                        playerView.player = controller.getPlayer()
                    }
                    playerView.resizeMode = scaleMode.resizeMode
                    playerView.subtitleView?.apply {
                        setStyle(
                            CaptionStyleCompat(
                                subtitleStyle.textColor.toInt(),
                                subtitleStyle.backgroundColor.toInt(),
                                0x00000000,
                                CaptionStyleCompat.EDGE_TYPE_OUTLINE,
                                0xFF000000.toInt(),
                                null
                            )
                        )
                        setFixedTextSize(android.util.TypedValue.COMPLEX_UNIT_SP, subtitleStyle.fontSizeSp)
                    }
                },
                modifier = Modifier.fillMaxSize()
            )
        }

        // Tap & Gesture Detector Layer (underneath controls, over video)
        Box(
            modifier = Modifier
                .fillMaxSize()
                .pointerInput(isLocked) {
                    if (isLocked) {
                        detectTapGestures {
                            showControls = !showControls
                        }
                    } else {
                        detectTapGestures(
                            onTap = {
                                showControls = !showControls
                            },
                            onDoubleTap = { offset ->
                                val isRightSide = offset.x > size.width / 2
                                if (isRightSide) {
                                    controller.seekRelative(10)
                                    doubleTapFeedback = "+10"
                                } else {
                                    controller.seekRelative(-10)
                                    doubleTapFeedback = "-10"
                                }
                            }
                        )
                    }
                }
        )

        // Gesture Overlay Feedback (Brightness, Volume, Fast Seeking)
        AnimatedVisibility(
            visible = gestureOverlayText != null,
            enter = fadeIn() + scaleIn(),
            exit = fadeOut() + scaleOut(),
            modifier = Modifier.align(Alignment.Center)
        ) {
            gestureOverlayText?.let { text ->
                Surface(
                    color = Color.Black.copy(alpha = 0.85f),
                    shape = RoundedCornerShape(12.dp),
                    border = androidx.compose.foundation.BorderStroke(1.dp, NeonRed)
                ) {
                    Column(
                        modifier = Modifier.padding(horizontal = 20.dp, vertical = 12.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Text(
                            text = text,
                            color = TextPrimary,
                            fontWeight = FontWeight.Bold,
                            fontSize = 15.sp,
                            letterSpacing = 1.sp
                        )
                    }
                }
            }
        }

        // Double Tap +/-10s Indicators
        AnimatedVisibility(
            visible = doubleTapFeedback != null,
            enter = fadeIn() + scaleIn(),
            exit = fadeOut() + scaleOut(),
            modifier = Modifier.align(
                if (doubleTapFeedback == "+10") Alignment.CenterEnd else Alignment.CenterStart
            )
        ) {
            Box(
                modifier = Modifier
                    .padding(24.dp)
                    .size(64.dp)
                    .background(NeonRed.copy(alpha = 0.3f), CircleShape)
                    .border(2.dp, NeonRed, CircleShape),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    text = doubleTapFeedback ?: "",
                    color = TextPrimary,
                    fontWeight = FontWeight.Black,
                    fontSize = 18.sp
                )
            }
        }

        // Loading Indicator
        if (diagnostics.isLoading) {
            Box(
                modifier = Modifier.fillMaxSize(),
                contentAlignment = Alignment.Center
            ) {
                CircularProgressIndicator(
                    color = NeonRed,
                    strokeWidth = 3.dp,
                    modifier = Modifier.size(46.dp)
                )
            }
        }

        // Error Banner
        if (diagnostics.errorMessage != null && !diagnostics.isLoading) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(Color.Black.copy(alpha = 0.75f)),
                contentAlignment = Alignment.Center
            ) {
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                    modifier = Modifier.padding(16.dp)
                ) {
                    Text(
                        text = "تعذر تشغيل هذا الرابط / البث",
                        color = NeonRed,
                        fontSize = 15.sp,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = diagnostics.errorMessage ?: "",
                        color = TextSecondary,
                        fontSize = 12.sp,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                        textAlign = TextAlign.Center
                    )
                    Button(
                        onClick = {
                            currentChannel?.let { controller.playChannel(it) }
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = NeonRedContainer),
                        shape = RoundedCornerShape(8.dp),
                        modifier = Modifier.border(1.dp, NeonRed, RoundedCornerShape(8.dp))
                    ) {
                        Icon(
                            imageVector = Icons.Default.Replay,
                            contentDescription = "Retry",
                            tint = NeonRed,
                            modifier = Modifier.size(16.dp)
                        )
                        Spacer(modifier = Modifier.width(6.dp))
                        Text("إعادة المحاولة", color = TextPrimary, fontSize = 13.sp)
                    }
                }
            }
        }

        // Main Player Controls Overlay
        AnimatedVisibility(
            visible = showControls,
            enter = fadeIn(),
            exit = fadeOut(),
            modifier = Modifier.fillMaxSize()
        ) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(
                        Brush.verticalGradient(
                            colors = listOf(
                                Color.Black.copy(alpha = 0.75f),
                                Color.Transparent,
                                Color.Black.copy(alpha = 0.85f)
                            )
                        )
                    )
            ) {
                if (isLocked) {
                    // Locked overlay: show only unlock button
                    IconButton(
                        onClick = { controller.toggleLock() },
                        modifier = Modifier
                            .align(Alignment.TopEnd)
                            .padding(12.dp)
                            .background(NeonRedContainer, CircleShape)
                            .border(1.dp, NeonRed, CircleShape)
                            .size(42.dp)
                    ) {
                        Icon(
                            imageVector = Icons.Default.Lock,
                            contentDescription = "Unlock Controls",
                            tint = NeonRed,
                            modifier = Modifier.size(22.dp)
                        )
                    }
                } else {
                    // Top Player Bar
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .align(Alignment.TopCenter)
                            .padding(horizontal = 8.dp, vertical = 6.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        // Left: Back, Channel Name, LIVE badge
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(6.dp),
                            modifier = Modifier.weight(1f, fill = false)
                        ) {
                            if (isFullscreen) {
                                IconButton(
                                    onClick = onToggleFullscreen,
                                    modifier = Modifier.size(34.dp)
                                ) {
                                    Icon(
                                        imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                                        contentDescription = "Back",
                                        tint = TextPrimary,
                                        modifier = Modifier.size(20.dp)
                                    )
                                }
                            }
                            Text(
                                text = currentChannel?.name ?: "Youseif Live Stream",
                                color = TextPrimary,
                                fontSize = 14.sp,
                                fontWeight = FontWeight.Bold,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis
                            )
                            if (diagnostics.isLive) {
                                LiveBadge(isLive = true)
                            }
                        }

                        // Right: Cast, PiP, Subtitles, Quality, Audio, More
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(2.dp)
                        ) {
                            // Cast Button
                            IconButton(
                                onClick = {
                                    Toast.makeText(context, "البحث عن أجهزة Cast متوافقة...", Toast.LENGTH_SHORT).show()
                                },
                                modifier = Modifier.size(32.dp)
                            ) {
                                Icon(
                                    imageVector = Icons.Default.Cast,
                                    contentDescription = "Cast",
                                    tint = TextSecondary,
                                    modifier = Modifier.size(18.dp)
                                )
                            }

                            // PiP Button
                            IconButton(
                                onClick = {
                                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                                        try {
                                            val params = PictureInPictureParams.Builder()
                                                .setAspectRatio(Rational(16, 9))
                                                .build()
                                            activity?.enterPictureInPictureMode(params)
                                        } catch (e: Throwable) {
                                            Toast.makeText(context, "PiP غير مدعوم", Toast.LENGTH_SHORT).show()
                                        }
                                    }
                                },
                                modifier = Modifier.size(32.dp)
                            ) {
                                Icon(
                                    imageVector = Icons.Default.PictureInPictureAlt,
                                    contentDescription = "Picture in Picture",
                                    tint = TextSecondary,
                                    modifier = Modifier.size(18.dp)
                                )
                            }

                            // Subtitles (CC) Button
                            IconButton(
                                onClick = { showSubtitleDialog = true },
                                modifier = Modifier.size(32.dp)
                            ) {
                                Icon(
                                    imageVector = Icons.Default.ClosedCaption,
                                    contentDescription = "Subtitles",
                                    tint = if (subtitleTracks.any { it.isSelected }) NeonRed else TextSecondary,
                                    modifier = Modifier.size(18.dp)
                                )
                            }

                            // HD / Quality Button
                            IconButton(
                                onClick = { showQualityDialog = true },
                                modifier = Modifier.size(32.dp)
                            ) {
                                Icon(
                                    imageVector = Icons.Default.HighQuality,
                                    contentDescription = "Quality HD",
                                    tint = NeonRed,
                                    modifier = Modifier.size(19.dp)
                                )
                            }

                            // Audio Boost & Tracks Button
                            IconButton(
                                onClick = { showAudioDialog = true },
                                modifier = Modifier.size(32.dp)
                            ) {
                                Icon(
                                    imageVector = Icons.Default.GraphicEq,
                                    contentDescription = "Audio Boost",
                                    tint = if (audioBoost != AudioBoostLevel.BOOST_100) NeonRed else TextSecondary,
                                    modifier = Modifier.size(19.dp)
                                )
                            }

                            // More Menu Button
                            Box {
                                IconButton(
                                    onClick = { showMoreMenu = true },
                                    modifier = Modifier.size(32.dp)
                                ) {
                                    Icon(
                                        imageVector = Icons.Default.MoreVert,
                                        contentDescription = "More",
                                        tint = TextSecondary,
                                        modifier = Modifier.size(19.dp)
                                    )
                                }

                                DropdownMenu(
                                    expanded = showMoreMenu,
                                    onDismissRequest = { showMoreMenu = false },
                                    modifier = Modifier
                                        .background(DarkSurface)
                                        .border(1.dp, CrimsonBorder, RoundedCornerShape(8.dp))
                                ) {
                                    DropdownMenuItem(
                                        text = { Text("سرعة التشغيل (${playbackSpeed}x)", color = TextPrimary) },
                                        leadingIcon = { Icon(Icons.Default.Speed, contentDescription = null, tint = NeonRed) },
                                        onClick = {
                                            showMoreMenu = false
                                            showSpeedDialog = true
                                        }
                                    )
                                    DropdownMenuItem(
                                        text = { Text("وضع الشاشة (${scaleMode.labelAr})", color = TextPrimary) },
                                        leadingIcon = { Icon(Icons.Default.AspectRatio, contentDescription = null, tint = NeonRed) },
                                        onClick = {
                                            showMoreMenu = false
                                            controller.cycleScaleMode()
                                        }
                                    )
                                    DropdownMenuItem(
                                        text = { Text("قفل عناصر التحكم", color = TextPrimary) },
                                        leadingIcon = { Icon(Icons.Default.Lock, contentDescription = null, tint = NeonRed) },
                                        onClick = {
                                            showMoreMenu = false
                                            controller.toggleLock()
                                        }
                                    )
                                    DropdownMenuItem(
                                        text = { Text("الإعدادات", color = TextPrimary) },
                                        leadingIcon = { Icon(Icons.Default.Settings, contentDescription = null, tint = NeonRed) },
                                        onClick = {
                                            showMoreMenu = false
                                            onOpenSettings()
                                        }
                                    )
                                }
                            }
                        }
                    }

                    // Upper Right Playlist button
                    IconButton(
                        onClick = onOpenPlaylist,
                        modifier = Modifier
                            .align(Alignment.TopEnd)
                            .padding(top = 44.dp, end = 10.dp)
                            .background(DarkSurface.copy(alpha = 0.8f), CircleShape)
                            .border(1.dp, CrimsonBorder, CircleShape)
                            .size(36.dp)
                    ) {
                        Icon(
                            imageVector = Icons.Default.PlaylistPlay,
                            contentDescription = "Playlist",
                            tint = NeonRed,
                            modifier = Modifier.size(20.dp)
                        )
                    }

                    // Center Playback Controls (Balanced & Clean)
                    Row(
                        modifier = Modifier
                            .align(Alignment.Center)
                            .fillMaxWidth(0.85f),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceEvenly
                    ) {
                        // Previous Channel / Rewind
                        IconButton(
                            onClick = onPreviousChannel,
                            modifier = Modifier
                                .size(42.dp)
                                .background(DarkSurface.copy(alpha = 0.7f), CircleShape)
                                .border(1.dp, CrimsonBorder, CircleShape)
                        ) {
                            Icon(
                                imageVector = Icons.Default.SkipPrevious,
                                contentDescription = "Previous Channel",
                                tint = TextPrimary,
                                modifier = Modifier.size(22.dp)
                            )
                        }

                        // -10s Back
                        IconButton(
                            onClick = { controller.seekRelative(-10) },
                            modifier = Modifier
                                .size(42.dp)
                                .background(DarkSurface.copy(alpha = 0.7f), CircleShape)
                                .border(1.dp, CrimsonBorder, CircleShape)
                        ) {
                            Icon(
                                imageVector = Icons.Default.Replay10,
                                contentDescription = "10s Back",
                                tint = TextPrimary,
                                modifier = Modifier.size(22.dp)
                            )
                        }

                        // EXACT CENTER MAIN PLAY / PAUSE BUTTON WITH NEON GLOW
                        Box(
                            modifier = Modifier
                                .size(64.dp)
                                .background(
                                    Brush.radialGradient(
                                        colors = listOf(NeonRed, NeonRed.copy(alpha = 0.4f), Color.Transparent)
                                    ),
                                    CircleShape
                                )
                                .border(2.dp, NeonRed, CircleShape)
                                .clickable { controller.togglePlayPause() },
                            contentAlignment = Alignment.Center
                        ) {
                            Icon(
                                imageVector = if (diagnostics.isPlaying) Icons.Default.Pause else Icons.Default.PlayArrow,
                                contentDescription = if (diagnostics.isPlaying) "Pause" else "Play",
                                tint = TextPrimary,
                                modifier = Modifier.size(34.dp)
                            )
                        }

                        // +10s Forward
                        IconButton(
                            onClick = { controller.seekRelative(10) },
                            modifier = Modifier
                                .size(42.dp)
                                .background(DarkSurface.copy(alpha = 0.7f), CircleShape)
                                .border(1.dp, CrimsonBorder, CircleShape)
                        ) {
                            Icon(
                                imageVector = Icons.Default.Forward10,
                                contentDescription = "10s Forward",
                                tint = TextPrimary,
                                modifier = Modifier.size(22.dp)
                            )
                        }

                        // Next Channel / Forward
                        IconButton(
                            onClick = onNextChannel,
                            modifier = Modifier
                                .size(42.dp)
                                .background(DarkSurface.copy(alpha = 0.7f), CircleShape)
                                .border(1.dp, CrimsonBorder, CircleShape)
                        ) {
                            Icon(
                                imageVector = Icons.Default.SkipNext,
                                contentDescription = "Next Channel",
                                tint = TextPrimary,
                                modifier = Modifier.size(22.dp)
                            )
                        }
                    }

                    // Bottom Bar: Seekbar, Time, Aspect Ratio, Lock, Mute, Fullscreen
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .align(Alignment.BottomCenter)
                            .padding(horizontal = 10.dp, vertical = 6.dp)
                    ) {
                        // Progress Slider
                        if (!diagnostics.isLive && diagnostics.totalDurationMs > 0) {
                            Slider(
                                value = diagnostics.currentPositionMs.toFloat(),
                                onValueChange = { targetPos ->
                                    controller.seekTo(targetPos.toLong())
                                },
                                valueRange = 0f..diagnostics.totalDurationMs.toFloat(),
                                colors = SliderDefaults.colors(
                                    thumbColor = NeonRed,
                                    activeTrackColor = NeonRed,
                                    inactiveTrackColor = DarkSurfaceVariant
                                ),
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .height(24.dp)
                            )
                        }

                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            // Left: Time elapsed / LIVE
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(6.dp)
                            ) {
                                if (diagnostics.isLive) {
                                    Text("بث مباشر", color = LiveRed, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                                } else {
                                    val curSec = diagnostics.currentPositionMs / 1000
                                    val totSec = diagnostics.totalDurationMs / 1000
                                    val curStr = String.format("%02d:%02d", curSec / 60, curSec % 60)
                                    val totStr = String.format("%02d:%02d", totSec / 60, totSec % 60)
                                    Text("$curStr / $totStr", color = TextSecondary, fontSize = 11.sp)
                                }
                            }

                            // Right: Three Screen Modes (FIT / FILL / CROP), Lock, Mute, Fullscreen
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(4.dp)
                            ) {
                                // Three Screen Modes Toggle Button
                                Surface(
                                    color = NeonRedContainer,
                                    shape = RoundedCornerShape(6.dp),
                                    border = androidx.compose.foundation.BorderStroke(1.dp, NeonRed),
                                    modifier = Modifier.clickable { controller.cycleScaleMode() }
                                ) {
                                    Text(
                                        text = scaleMode.labelAr,
                                        color = TextPrimary,
                                        fontSize = 11.sp,
                                        fontWeight = FontWeight.Bold,
                                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp)
                                    )
                                }

                                // Mute Button
                                IconButton(
                                    onClick = { controller.toggleMute() },
                                    modifier = Modifier.size(30.dp)
                                ) {
                                    Icon(
                                        imageVector = if (isMuted) Icons.Default.VolumeOff else Icons.Default.VolumeUp,
                                        contentDescription = "Mute",
                                        tint = if (isMuted) NeonRed else TextSecondary,
                                        modifier = Modifier.size(18.dp)
                                    )
                                }

                                // Lock Button
                                IconButton(
                                    onClick = { controller.toggleLock() },
                                    modifier = Modifier.size(30.dp)
                                ) {
                                    Icon(
                                        imageVector = Icons.Default.LockOpen,
                                        contentDescription = "Lock",
                                        tint = TextSecondary,
                                        modifier = Modifier.size(18.dp)
                                    )
                                }

                                // Fullscreen Button
                                IconButton(
                                    onClick = onToggleFullscreen,
                                    modifier = Modifier.size(30.dp)
                                ) {
                                    Icon(
                                        imageVector = if (isFullscreen) Icons.Default.FullscreenExit else Icons.Default.Fullscreen,
                                        contentDescription = "Fullscreen",
                                        tint = TextPrimary,
                                        modifier = Modifier.size(20.dp)
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // QUALITY (HD) SELECTION DIALOG
    if (showQualityDialog) {
        AlertDialog(
            onDismissRequest = { showQualityDialog = false },
            containerColor = DarkSurface,
            title = {
                Text("جودة الفيديو / الدقة", color = TextPrimary, fontWeight = FontWeight.Bold, fontSize = 16.sp)
            },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    if (videoTracks.isEmpty()) {
                        Text("جودة تلقائية (Auto Adaptive HD)", color = TextSecondary, fontSize = 14.sp)
                    } else {
                        videoTracks.forEach { track ->
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clip(RoundedCornerShape(8.dp))
                                    .background(if (track.isSelected) NeonRedContainer else Color.Transparent)
                                    .clickable {
                                        controller.selectTrack(C.TRACK_TYPE_VIDEO, track.groupIndex, track.trackIndex)
                                        showQualityDialog = false
                                    }
                                    .padding(10.dp),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Text(track.name, color = if (track.isSelected) NeonRed else TextPrimary, fontSize = 14.sp)
                                if (track.isSelected) {
                                    Text("محدد", color = NeonRed, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                                }
                            }
                        }
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = { showQualityDialog = false }) {
                    Text("إغلاق", color = NeonRed)
                }
            }
        )
    }

    // AUDIO BOOST & TRACKS DIALOG
    if (showAudioDialog) {
        AlertDialog(
            onDismissRequest = { showAudioDialog = false },
            containerColor = DarkSurface,
            title = {
                Text("تعزيز الصوت والمسارات", color = TextPrimary, fontWeight = FontWeight.Bold, fontSize = 16.sp)
            },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("مستوى تعزيز الصوت (Audio Boost):", color = TextSecondary, fontSize = 13.sp)
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        AudioBoostLevel.values().forEach { level ->
                            val isSel = audioBoost == level
                            Surface(
                                color = if (isSel) NeonRed else DarkCardBg,
                                shape = RoundedCornerShape(6.dp),
                                border = androidx.compose.foundation.BorderStroke(1.dp, if (isSel) NeonRed else CrimsonBorder),
                                modifier = Modifier.clickable { controller.setAudioBoost(level) }
                            ) {
                                Text(
                                    text = "${level.percentage}%",
                                    color = if (isSel) Color.White else TextSecondary,
                                    fontSize = 11.sp,
                                    fontWeight = if (isSel) FontWeight.Bold else FontWeight.Normal,
                                    modifier = Modifier.padding(horizontal = 6.dp, vertical = 4.dp)
                                )
                            }
                        }
                    }

                    if (audioTracks.isNotEmpty()) {
                        Spacer(modifier = Modifier.height(4.dp))
                        Text("المسار الصوتي (Audio Track):", color = TextSecondary, fontSize = 13.sp)
                        audioTracks.forEach { track ->
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clip(RoundedCornerShape(8.dp))
                                    .background(if (track.isSelected) NeonRedContainer else Color.Transparent)
                                    .clickable {
                                        controller.selectTrack(C.TRACK_TYPE_AUDIO, track.groupIndex, track.trackIndex)
                                    }
                                    .padding(8.dp),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Text(track.name, color = if (track.isSelected) NeonRed else TextPrimary, fontSize = 13.sp)
                                if (track.isSelected) {
                                    Text("نشط", color = NeonRed, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                                }
                            }
                        }
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = { showAudioDialog = false }) {
                    Text("تم", color = NeonRed)
                }
            }
        )
    }

    // SUBTITLE CONTROLS DIALOG
    if (showSubtitleDialog) {
        var externalSubUrl by remember { mutableStateOf("") }
        var selectedFontSize by remember { mutableFloatStateOf(subtitleStyle.fontSizeSp) }
        var selectedColor by remember { mutableLongStateOf(subtitleStyle.textColor) }

        AlertDialog(
            onDismissRequest = { showSubtitleDialog = false },
            containerColor = DarkSurface,
            title = {
                Text("إعدادات الترجمة (Subtitles CC)", color = TextPrimary, fontWeight = FontWeight.Bold, fontSize = 16.sp)
            },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text("الترجمة المدمجة:", color = TextSecondary, fontSize = 13.sp)
                        Button(
                            onClick = {
                                val hasActive = subtitleTracks.any { it.isSelected }
                                controller.setSubtitlesEnabled(!hasActive)
                            },
                            colors = ButtonDefaults.buttonColors(containerColor = NeonRedContainer),
                            shape = RoundedCornerShape(6.dp),
                            modifier = Modifier.border(1.dp, NeonRed, RoundedCornerShape(6.dp))
                        ) {
                            Text(
                                if (subtitleTracks.any { it.isSelected }) "إيقاف الترجمة" else "تفعيل الترجمة",
                                color = TextPrimary,
                                fontSize = 11.sp
                            )
                        }
                    }

                    if (subtitleTracks.isNotEmpty()) {
                        subtitleTracks.forEach { track ->
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clip(RoundedCornerShape(6.dp))
                                    .background(if (track.isSelected) NeonRedContainer else Color.Transparent)
                                    .clickable {
                                        controller.selectTrack(C.TRACK_TYPE_TEXT, track.groupIndex, track.trackIndex)
                                    }
                                    .padding(6.dp),
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Text(track.name, color = if (track.isSelected) NeonRed else TextPrimary, fontSize = 13.sp)
                                if (track.isSelected) Text("مفعل", color = NeonRed, fontSize = 11.sp)
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(4.dp))
                    Text("إضافة رابط ترجمة خارجي (SRT/VTT):", color = TextSecondary, fontSize = 12.sp)
                    OutlinedTextField(
                        value = externalSubUrl,
                        onValueChange = { externalSubUrl = it },
                        placeholder = { Text("https://example.com/sub.srt", color = TextMuted, fontSize = 12.sp) },
                        modifier = Modifier.fillMaxWidth(),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = NeonRed,
                            unfocusedBorderColor = CrimsonBorder,
                            focusedTextColor = TextPrimary,
                            unfocusedTextColor = TextPrimary
                        ),
                        singleLine = true
                    )

                    // Subtitle Font Size options
                    Text("حجم الخط:", color = TextSecondary, fontSize = 12.sp)
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        listOf("صغير" to 14f, "متوسط" to 18f, "كبير" to 22f, "كبير جداً" to 26f).forEach { (label, size) ->
                            val isSel = selectedFontSize == size
                            Surface(
                                color = if (isSel) NeonRed else DarkCardBg,
                                shape = RoundedCornerShape(6.dp),
                                modifier = Modifier.clickable {
                                    selectedFontSize = size
                                    controller.updateSubtitleStyle(subtitleStyle.copy(fontSizeSp = size))
                                }
                            ) {
                                Text(
                                    label,
                                    color = if (isSel) Color.White else TextSecondary,
                                    fontSize = 11.sp,
                                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                                )
                            }
                        }
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    if (externalSubUrl.isNotBlank()) {
                        currentChannel?.let {
                            controller.playUrl(it.url, it.name, it.isLive, externalSubtitleUrl = externalSubUrl)
                        }
                    }
                    showSubtitleDialog = false
                }) {
                    Text("تطبيق وإغلاق", color = NeonRed)
                }
            }
        )
    }

    // PLAYBACK SPEED DIALOG
    if (showSpeedDialog) {
        AlertDialog(
            onDismissRequest = { showSpeedDialog = false },
            containerColor = DarkSurface,
            title = {
                Text("سرعة التشغيل", color = TextPrimary, fontWeight = FontWeight.Bold, fontSize = 16.sp)
            },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    listOf(0.5f, 0.75f, 1.0f, 1.25f, 1.5f, 2.0f).forEach { speed ->
                        val isSel = playbackSpeed == speed
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clip(RoundedCornerShape(8.dp))
                                .background(if (isSel) NeonRedContainer else Color.Transparent)
                                .clickable {
                                    controller.setPlaybackSpeed(speed)
                                    showSpeedDialog = false
                                }
                                .padding(10.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text("${speed}x", color = if (isSel) NeonRed else TextPrimary, fontSize = 14.sp)
                            if (isSel) {
                                Text("السرعة الحالية", color = NeonRed, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                            }
                        }
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = { showSpeedDialog = false }) {
                    Text("إلغاء", color = NeonRed)
                }
            }
        )
    }
}
