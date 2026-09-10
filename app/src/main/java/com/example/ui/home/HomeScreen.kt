package com.example.ui.home

import android.content.Context
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Clear
import androidx.compose.material.icons.filled.ContentPaste
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import com.example.data.PlaylistItem
import com.example.data.HistoryItem
import com.example.player.YouseifPlayerController
import com.example.ui.components.DiagnosticDashboardCards
import com.example.ui.components.PlayerTopBar
import com.example.ui.components.VideoPlayerView
import com.example.ui.components.visualScreenBackground
import com.example.ui.theme.AmoledBlack
import com.example.ui.theme.CrimsonBorder
import com.example.ui.theme.DarkCardBg
import com.example.ui.theme.DarkSurface
import com.example.ui.theme.LiveGreen
import com.example.ui.theme.NeonRed
import com.example.ui.theme.NeonRedContainer
import com.example.ui.theme.TextMuted
import com.example.ui.theme.TextPrimary
import com.example.ui.theme.TextSecondary
import com.example.ui.theme.TechCyan

@Composable
fun HomeScreen(
    controller: YouseifPlayerController,
    recentChannels: List<PlaylistItem>,
    recentHistory: List<HistoryItem> = emptyList(),
    onChannelSelected: (PlaylistItem) -> Unit,
    onNavigateToChannels: () -> Unit,
    onNavigateToSettings: () -> Unit,
    onToggleFullscreen: () -> Unit,
    onImportM3U: (String) -> Unit,
    onHistoryUrl: (String, String) -> Unit = { _, _ -> }
) {
    val clipboardManager = LocalClipboardManager.current
    val diagnostics by controller.diagnostics.collectAsState()
    val currentChannel by controller.currentChannel.collectAsState()

    var urlInput by remember { mutableStateOf("") }

    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .visualScreenBackground(),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        // 1. Unified reference top bar with the exact 3D icon language.
        item {
            PlayerTopBar(
                onMenu = onNavigateToChannels,
                onRefresh = { currentChannel?.let { controller.playChannel(it) } },
                onInfo = onNavigateToSettings
            )
        }

        // 2. Status Row: ● PLAYING
        item {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                Box(
                    modifier = Modifier
                        .size(7.dp)
                        .clip(CircleShape)
                        .background(if (diagnostics.isPlaying) NeonRed else TextMuted)
                )
                Text(
                    text = if (diagnostics.isPlaying) "PLAYING" else "READY",
                    color = if (diagnostics.isPlaying) NeonRed else TextMuted,
                    fontSize = 11.5.sp,
                    fontWeight = FontWeight.Bold,
                    letterSpacing = 1.sp
                )
            }
        }

        // 3. Search / URL Input Box with integrated PASTE action
        item {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 14.dp)
            ) {
                OutlinedTextField(
                    value = urlInput,
                    onValueChange = { urlInput = it },
                    modifier = Modifier
                        .fillMaxWidth()
                        .testTag("stream_url_input"),
                    placeholder = {
                        Text(
                            text = "Paste video URL or stream link",
                            color = TextMuted,
                            fontSize = 12.sp,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                    },
                    trailingIcon = {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(4.dp),
                            modifier = Modifier.padding(end = 4.dp)
                        ) {
                            // 1. Clear text button if input is not empty
                            if (urlInput.isNotEmpty()) {
                                IconButton(
                                    onClick = { urlInput = "" },
                                    modifier = Modifier.size(28.dp)
                                ) {
                                    Icon(
                                        imageVector = Icons.Default.Clear,
                                        contentDescription = "Clear",
                                        tint = TextMuted,
                                        modifier = Modifier.size(16.dp)
                                    )
                                }
                            }

                            // 2. Paste / Clipboard Icon Button (pastes clipboard text directly into input)
                            IconButton(
                                onClick = {
                                    val clip = clipboardManager.getText()?.text?.trim()
                                    if (!clip.isNullOrBlank()) {
                                        urlInput = clip
                                    }
                                },
                                modifier = Modifier
                                    .size(32.dp)
                                    .testTag("paste_clipboard_button")
                            ) {
                                Icon(
                                    imageVector = Icons.Default.ContentPaste,
                                    contentDescription = "Paste from Clipboard",
                                    tint = if (urlInput.isEmpty()) NeonRed else TextMuted,
                                    modifier = Modifier.size(18.dp)
                                )
                            }

                            // 3. Main Action Button: ▶ PLAY
                            Button(
                                onClick = {
                                    val target = if (urlInput.isNotBlank()) {
                                        urlInput.trim()
                                    } else {
                                        clipboardManager.getText()?.text?.trim() ?: ""
                                    }
                                    if (target.isNotBlank()) {
                                        urlInput = target
                                        controller.playUrl(target, "Custom Stream", true)
                                        onHistoryUrl("Custom Stream", target)
                                    }
                                },
                                modifier = Modifier
                                    .height(34.dp)
                                    .testTag("play_url_submit_button"),
                                colors = ButtonDefaults.buttonColors(
                                    containerColor = NeonRed,
                                    contentColor = Color.White
                                ),
                                shape = RoundedCornerShape(6.dp),
                                contentPadding = androidx.compose.foundation.layout.PaddingValues(
                                    horizontal = 10.dp,
                                    vertical = 0.dp
                                )
                            ) {
                                Icon(
                                    imageVector = Icons.Default.PlayArrow,
                                    contentDescription = "Play",
                                    tint = Color.White,
                                    modifier = Modifier.size(16.dp)
                                )
                                Spacer(modifier = Modifier.width(3.dp))
                                Text(
                                    text = "PLAY",
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Black,
                                    letterSpacing = 0.5.sp
                                )
                            }
                        }
                    },
                    singleLine = true,
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedContainerColor = DarkSurface,
                        unfocusedContainerColor = DarkSurface,
                        focusedBorderColor = NeonRed,
                        unfocusedBorderColor = CrimsonBorder,
                        focusedTextColor = TextPrimary,
                        unfocusedTextColor = TextPrimary
                    ),
                    shape = RoundedCornerShape(8.dp),
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Go),
                    keyboardActions = KeyboardActions(
                        onGo = {
                            val target = if (urlInput.isNotBlank()) urlInput.trim() else clipboardManager.getText()?.text?.trim() ?: ""
                            if (target.isNotBlank()) {
                                urlInput = target
                                controller.playUrl(target, "Custom Stream", true)
                                onHistoryUrl("Custom Stream", target)
                            }
                        }
                    )
                )
            }
        }

        // 4. 16:9 Video Player View
        item {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 14.dp)
            ) {
                VideoPlayerView(
                    controller = controller,
                    modifier = Modifier
                        .fillMaxWidth()
                        .aspectRatio(16f / 9f)
                        .clip(RoundedCornerShape(8.dp))
                        .border(1.dp, CrimsonBorder, RoundedCornerShape(8.dp)),
                    isFullscreen = false,
                    onToggleFullscreen = onToggleFullscreen,
                    onPreviousChannel = {
                        val currentIndex = recentChannels.indexOfFirst { it.id == currentChannel?.id }
                        if (currentIndex > 0) {
                            onChannelSelected(recentChannels[currentIndex - 1])
                        }
                    },
                    onNextChannel = {
                        val currentIndex = recentChannels.indexOfFirst { it.id == currentChannel?.id }
                        if (currentIndex != -1 && currentIndex < recentChannels.size - 1) {
                            onChannelSelected(recentChannels[currentIndex + 1])
                        }
                    },
                    onOpenPlaylist = onNavigateToChannels,
                    onOpenSettings = onNavigateToSettings
                )
            }
        }

        // 5. Diagnostic Dashboard Cards: Side-by-side STREAM INFO & CONNECTION
        item {
            DiagnosticDashboardCards(diagnostics = diagnostics)
        }

        // 6. Recently Played replaces the old Suggested Channels area.
        item {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 14.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Column {
                        Text("RECENTLY PLAYED", color = TextPrimary, fontSize = 14.sp, fontWeight = FontWeight.Black, letterSpacing = 1.sp)
                        Text("Your playback history", color = TextMuted, fontSize = 10.sp)
                    }
                    if (recentHistory.isNotEmpty()) {
                        Text("${recentHistory.size} items", color = NeonRedGlow, fontSize = 9.sp, fontWeight = FontWeight.Bold)
                    }
                }

                if (recentHistory.isEmpty()) {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(82.dp)
                            .clip(RoundedCornerShape(20.dp))
                            .background(
                                Brush.horizontalGradient(listOf(NeonRed.copy(alpha = .10f), TechCyan.copy(alpha = .06f)))
                            )
                            .border(1.dp, CrimsonBorder.copy(alpha = .55f), RoundedCornerShape(20.dp)),
                        contentAlignment = Alignment.Center
                    ) {
                        Text("No recently played items yet", color = TextMuted, fontSize = 11.sp)
                    }
                } else {
                    LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        items(recentHistory.take(12), key = { it.id }) { item ->
                            HistoryCard(item = item, onClick = {
                                controller.playUrl(item.url, item.title, true)
                            })
                        }
                    }
                }
            }
        }

        item { Spacer(modifier = Modifier.height(16.dp)) }
    }
}

@Composable
private fun HistoryCard(item: HistoryItem, onClick: () -> Unit) {
    Column(
        modifier = Modifier
            .width(154.dp)
            .height(92.dp)
            .clip(RoundedCornerShape(18.dp))
            .background(
                Brush.linearGradient(listOf(DarkCardBg.copy(alpha = .94f), DarkSurfaceVariant.copy(alpha = .72f)))
            )
            .border(1.dp, CrimsonBorder.copy(alpha = .72f), RoundedCornerShape(18.dp))
            .clickable(onClick = onClick)
            .padding(10.dp),
        verticalArrangement = Arrangement.SpaceBetween
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            AsyncImage(
                model = item.logoUrl.ifBlank { null },
                contentDescription = item.title,
                modifier = Modifier.size(34.dp).clip(RoundedCornerShape(10.dp)).background(DarkSurface)
            )
            Text(item.title, color = TextPrimary, fontSize = 11.sp, fontWeight = FontWeight.Bold, maxLines = 2, overflow = TextOverflow.Ellipsis)
        }
        Text(item.group, color = NeonRedGlow, fontSize = 8.sp, fontWeight = FontWeight.Bold, maxLines = 1)
    }
}
