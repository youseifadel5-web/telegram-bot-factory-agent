package com.example.ui

import android.app.Activity
import android.content.pm.ActivityInfo
import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.clip
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Animation
import androidx.compose.material.icons.filled.GridView
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Movie
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.outlined.Animation
import androidx.compose.material.icons.outlined.GridView
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.Movie
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material3.Icon
import androidx.compose.foundation.Image
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import com.example.R
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import com.example.data.PlaylistItem
import com.example.player.YouseifPlayerController
import com.example.ui.cartoons.CartoonsScreen
import com.example.ui.channels.ChannelsScreen
import com.example.ui.components.VideoPlayerView
import com.example.ui.components.visualScreenBackground
import com.example.ui.films.FilmsScreen
import com.example.ui.home.HomeScreen
import com.example.ui.settings.SettingsScreen
import com.example.ui.theme.AmoledBlack
import com.example.ui.theme.CrimsonBorder
import com.example.ui.theme.DarkSurface
import com.example.ui.theme.NeonRed
import com.example.ui.theme.NeonRedContainer
import com.example.ui.theme.NeonRedGlow
import com.example.ui.theme.TechCyan
import com.example.ui.theme.TextMuted

enum class AppTab(
    val label: String,
    val selectedIcon: ImageVector,
    val unselectedIcon: ImageVector
) {
    HOME("HOME", Icons.Filled.Home, Icons.Outlined.Home),
    CHANNELS("CHANNELS", Icons.Filled.GridView, Icons.Outlined.GridView),
    FILMS("Films", Icons.Filled.Movie, Icons.Outlined.Movie),
    CARTOON("Cartoon", Icons.Filled.Animation, Icons.Outlined.Animation),
    SETTINGS("SETTINGS", Icons.Filled.Settings, Icons.Outlined.Settings)
}

@Composable
fun MainScreen(
    controller: YouseifPlayerController,
    channels: List<PlaylistItem>,
    films: List<PlaylistItem>,
    cartoons: List<PlaylistItem>,
    recentHistory: List<com.example.data.HistoryItem> = emptyList(),
    selectedTheme: String = "PURPLE",
    onThemeSelected: (String) -> Unit = {},
    onToggleFavorite: (String, Boolean) -> Unit,
    onAddCustomChannel: (PlaylistItem) -> Unit,
    onImportM3U: (String) -> Unit,
    onDeleteChannel: (PlaylistItem) -> Unit,
    onResetChannels: () -> Unit,
    onClearCache: () -> Unit,
    onHistoryItem: (PlaylistItem) -> Unit = {},
    onHistoryUrl: (String, String) -> Unit = { _, _ -> }
) {
    val context = LocalContext.current
    val activity = context as? Activity
    var currentTab by remember { mutableStateOf(AppTab.HOME) }
    var isFullscreen by remember { mutableStateOf(false) }

    val currentPlayingChannel by controller.currentChannel.collectAsState()

    fun toggleFullscreenMode(fullscreen: Boolean) {
        isFullscreen = fullscreen
        activity?.let { act ->
            val window = act.window
            val insetsController = WindowCompat.getInsetsController(window, window.decorView)
            if (fullscreen) {
                act.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
                insetsController.hide(WindowInsetsCompat.Type.systemBars())
                insetsController.systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            } else {
                act.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
                insetsController.show(WindowInsetsCompat.Type.systemBars())
            }
        }
    }

    BackHandler(enabled = isFullscreen) {
        toggleFullscreenMode(false)
    }

    if (isFullscreen) {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(AmoledBlack)
        ) {
            VideoPlayerView(
                controller = controller,
                isFullscreen = true,
                onToggleFullscreen = { toggleFullscreenMode(false) },
                onPreviousChannel = {
                    val currentIndex = channels.indexOfFirst { it.id == currentPlayingChannel?.id }
                    if (currentIndex > 0) {
                        controller.playChannel(channels[currentIndex - 1])
                        onHistoryItem(channels[currentIndex - 1])
                    }
                },
                onNextChannel = {
                    val currentIndex = channels.indexOfFirst { it.id == currentPlayingChannel?.id }
                    if (currentIndex != -1 && currentIndex < channels.size - 1) {
                        controller.playChannel(channels[currentIndex + 1])
                        onHistoryItem(channels[currentIndex + 1])
                    }
                },
                onOpenPlaylist = {
                    toggleFullscreenMode(false)
                    currentTab = AppTab.CHANNELS
                },
                onOpenSettings = {
                    toggleFullscreenMode(false)
                    currentTab = AppTab.SETTINGS
                }
            )
        }
    } else {
        Scaffold(
            modifier = Modifier.fillMaxSize(),
            containerColor = AmoledBlack,
            bottomBar = {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 12.dp, vertical = 7.dp)
                        .navigationBarsPadding()
                        .clip(RoundedCornerShape(30.dp))
                        .background(Brush.linearGradient(listOf(NeonRedContainer.copy(alpha = .32f), DarkSurface.copy(alpha = .94f), TechCyan.copy(alpha = .10f))))
                        .border(1.dp, CrimsonBorder.copy(alpha = .90f), RoundedCornerShape(30.dp))
                ) {
                    NavigationBar(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(70.dp),
                        containerColor = Color.Transparent,
                        tonalElevation = 0.dp
                    ) {
                        AppTab.values().forEach { tab ->
                            val isSelected = currentTab == tab
                            NavigationBarItem(
                                selected = isSelected,
                                onClick = { currentTab = tab },
                                icon = {
                                    Image(
                                        painter = painterResource(
                                            when (tab) {
                                                AppTab.HOME -> R.drawable.home
                                                AppTab.CHANNELS -> R.drawable.channels
                                                AppTab.FILMS -> R.drawable.films
                                                AppTab.CARTOON -> R.drawable.films
                                                AppTab.SETTINGS -> R.drawable.settings
                                            }
                                        ),
                                        contentDescription = tab.label,
                                        contentScale = ContentScale.Fit,
                                        modifier = Modifier.size(if (isSelected) 28.dp else 24.dp)
                                    )
                                },
                                label = {
                                    Text(
                                        text = tab.label,
                                        fontSize = 9.sp,
                                        fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Medium,
                                        color = if (isSelected) NeonRedGlow else TextMuted
                                    )
                                },
                                colors = NavigationBarItemDefaults.colors(
                                    selectedIconColor = NeonRed,
                                    unselectedIconColor = TextMuted,
                                    selectedTextColor = NeonRedGlow,
                                    unselectedTextColor = TextMuted,
                                    indicatorColor = NeonRedContainer.copy(alpha = .35f)
                                ),
                                modifier = Modifier.testTag("nav_tab_${tab.name.lowercase()}")
                            )
                        }
                    }
                }
            }
        ) { innerPadding ->
            Box(
                modifier = Modifier
                    .fillMaxSize()
                .padding(innerPadding)
            ) {
                AnimatedContent(
                    targetState = currentTab,
                    transitionSpec = { fadeIn() togetherWith fadeOut() },
                    label = "tab_animation"
                ) { tab ->
                    when (tab) {
                        AppTab.HOME -> {
                            HomeScreen(
                                controller = controller,
                                recentChannels = channels,
                                recentHistory = recentHistory,
                                onChannelSelected = { ch ->
                                    controller.playChannel(ch)
                                    onHistoryItem(ch)
                                },
                                onNavigateToChannels = { currentTab = AppTab.CHANNELS },
                                onNavigateToSettings = { currentTab = AppTab.SETTINGS },
                                onToggleFullscreen = { toggleFullscreenMode(true) },
                                onImportM3U = onImportM3U,
                                onHistoryUrl = onHistoryUrl
                            )
                        }
                        AppTab.CHANNELS -> {
                            ChannelsScreen(
                                channels = channels,
                                currentPlayingChannel = currentPlayingChannel,
                                onChannelSelected = { ch ->
                                    controller.playChannel(ch)
                                    onHistoryItem(ch)
                                    currentTab = AppTab.HOME
                                },
                                onToggleFavorite = onToggleFavorite,
                                onAddCustomChannel = onAddCustomChannel,
                                onImportM3U = onImportM3U,
                                onDeleteChannel = onDeleteChannel
                            )
                        }
                        AppTab.FILMS -> {
                            FilmsScreen(
                                films = films,
                                currentPlayingId = currentPlayingChannel?.id,
                                onFilmSelected = { film ->
                                    controller.playChannel(film)
                                    onHistoryItem(film)
                                    currentTab = AppTab.HOME
                                }
                            )
                        }
                        AppTab.CARTOON -> {
                            CartoonsScreen(
                                cartoons = cartoons,
                                currentPlayingId = currentPlayingChannel?.id,
                                onCartoonSelected = { cartoon ->
                                    controller.playChannel(cartoon)
                                    onHistoryItem(cartoon)
                                    currentTab = AppTab.HOME
                                }
                            )
                        }
                        AppTab.SETTINGS -> {
                            SettingsScreen(
                                selectedTheme = selectedTheme,
                                onThemeSelected = onThemeSelected,
                                onResetChannels = onResetChannels,
                                onClearCache = onClearCache,
                                onNavigateToChannels = { currentTab = AppTab.CHANNELS }
                            )
                        }
                    }
                }
            }
        }
    }
}
