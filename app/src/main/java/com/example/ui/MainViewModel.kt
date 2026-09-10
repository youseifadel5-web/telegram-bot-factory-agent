package com.example.ui

import android.app.Application
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.example.data.AppDatabase
import com.example.data.DefaultChannels
import com.example.data.M3UParser
import com.example.data.PlaylistItem
import com.example.player.YouseifPlayerController
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

class MainViewModel(application: Application) : AndroidViewModel(application) {

    private val db = AppDatabase.getInstance(application)
    private val channelDao = db.channelDao()
    private val historyDao = db.historyDao()

    val playerController = YouseifPlayerController(application, viewModelScope)

    val channels: StateFlow<List<PlaylistItem>> = channelDao.getAllChannels()
        .catch { e ->
            Log.e("MainViewModel", "Error fetching channels flow", e)
            emit(emptyList())
        }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    val recentHistory = historyDao.getRecentHistory()
        .catch { e ->
            Log.e("MainViewModel", "Error fetching history flow", e)
            emit(emptyList())
        }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    private val _films = MutableStateFlow<List<PlaylistItem>>(emptyList())
    val films: StateFlow<List<PlaylistItem>> = _films.asStateFlow()

    private val _cartoons = MutableStateFlow(DefaultChannels.CARTOONS)
    val cartoons: StateFlow<List<PlaylistItem>> = _cartoons.asStateFlow()

    init {
        // Start empty: no demo/default channels are injected automatically.
        // User playlists/imports remain intact; playback starts only after a real selection.
        viewModelScope.launch(Dispatchers.IO) {
            try {
                // Remove only built-in/demo rows from older builds; keep imported/custom playlists.
                channelDao.clearBuiltInChannels()
            } catch (e: Throwable) {
                Log.e("MainViewModel", "Error cleaning demo channels", e)
            }
        }
    }

    fun recordHistory(item: PlaylistItem) {
        viewModelScope.launch(Dispatchers.IO) {
            try {
                historyDao.insertHistory(
                    com.example.data.HistoryItem(
                        title = item.name,
                        url = item.url,
                        group = item.group,
                        logoUrl = item.logoUrl
                    )
                )
            } catch (e: Throwable) {
                Log.e("MainViewModel", "Error recording history", e)
            }
        }
    }

    fun recordHistory(title: String, url: String, group: String = "LIVE", logoUrl: String = "") {
        viewModelScope.launch(Dispatchers.IO) {
            try {
                historyDao.insertHistory(
                    com.example.data.HistoryItem(title = title, url = url, group = group, logoUrl = logoUrl)
                )
            } catch (e: Throwable) {
                Log.e("MainViewModel", "Error recording custom history", e)
            }
        }
    }

    fun toggleFavorite(id: String, isFavorite: Boolean) {
        viewModelScope.launch(Dispatchers.IO) {
            try {
                channelDao.setFavorite(id, isFavorite)
            } catch (e: Throwable) {
                Log.e("MainViewModel", "Error toggling favorite", e)
            }
        }
    }

    fun addCustomChannel(channel: PlaylistItem) {
        viewModelScope.launch(Dispatchers.IO) {
            try {
                channelDao.insertChannel(channel)
            } catch (e: Throwable) {
                Log.e("MainViewModel", "Error adding custom channel", e)
            }
        }
    }

    fun importM3U(m3uContent: String) {
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val parsed = M3UParser.parse(m3uContent)
                if (parsed.isNotEmpty()) {
                    channelDao.insertChannels(parsed)
                    withContext(Dispatchers.Main) {
                        playerController.playChannel(parsed.first())
                    }
                }
            } catch (e: Throwable) {
                Log.e("MainViewModel", "Error importing M3U", e)
            }
        }
    }

    fun deleteChannel(channel: PlaylistItem) {
        viewModelScope.launch(Dispatchers.IO) {
            try {
                channelDao.deleteChannel(channel)
            } catch (e: Throwable) {
                Log.e("MainViewModel", "Error deleting channel", e)
            }
        }
    }

    fun resetDefaultChannels() {
        viewModelScope.launch(Dispatchers.IO) {
            try {
                channelDao.clearBuiltInChannels()
            } catch (e: Throwable) {
                Log.e("MainViewModel", "Error clearing built-in channels", e)
            }
        }
    }

    fun clearCache() {
        viewModelScope.launch(Dispatchers.IO) {
            try {
                historyDao.clearHistory()
            } catch (e: Throwable) {
                Log.e("MainViewModel", "Error clearing cache", e)
            }
        }
    }

    override fun onCleared() {
        super.onCleared()
        playerController.release()
    }
}
