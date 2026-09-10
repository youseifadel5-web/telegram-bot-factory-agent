package com.example

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.example.ui.MainScreen
import com.example.ui.MainViewModel
import com.example.ui.theme.MyApplicationTheme
import com.example.ui.theme.applyPlayerTheme

class MainActivity : ComponentActivity() {
    private val viewModel: MainViewModel by viewModels()
    private var selectedTheme by mutableStateOf("PURPLE")

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        selectedTheme = getSharedPreferences("youseif_visual", MODE_PRIVATE)
            .getString("theme", "PURPLE") ?: "PURPLE"
        applyPlayerTheme(selectedTheme)
        enableEdgeToEdge()
        setContent {
            MyApplicationTheme {
                val channels by viewModel.channels.collectAsState()
                val films by viewModel.films.collectAsState()
                val cartoons by viewModel.cartoons.collectAsState()
                val recentHistory by viewModel.recentHistory.collectAsState()

                MainScreen(
                    controller = viewModel.playerController,
                    channels = channels,
                    films = films,
                    cartoons = cartoons,
                    recentHistory = recentHistory,
                    selectedTheme = selectedTheme,
                    onThemeSelected = { theme ->
                        selectedTheme = theme
                        applyPlayerTheme(theme)
                        getSharedPreferences("youseif_visual", MODE_PRIVATE)
                            .edit().putString("theme", theme).apply()
                    },
                    onToggleFavorite = { id, fav -> viewModel.toggleFavorite(id, fav) },
                    onAddCustomChannel = { ch -> viewModel.addCustomChannel(ch) },
                    onImportM3U = { m3u -> viewModel.importM3U(m3u) },
                    onDeleteChannel = { ch -> viewModel.deleteChannel(ch) },
                    onResetChannels = { viewModel.resetDefaultChannels() },
                    onClearCache = { viewModel.clearCache() },
                    onHistoryItem = { item -> viewModel.recordHistory(item) },
                    onHistoryUrl = { title, url -> viewModel.recordHistory(title, url) }
                )
            }
        }
    }
}
