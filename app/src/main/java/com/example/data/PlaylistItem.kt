package com.example.data

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "channels")
data class PlaylistItem(
    @PrimaryKey
    val id: String,
    val channelNumber: Int,
    val name: String,
    val url: String,
    val group: String = "GENERAL",
    val logoUrl: String = "",
    val language: String = "EN",
    val isLive: Boolean = true,
    val httpUserAgent: String? = null,
    val httpReferrer: String? = null,
    val isFavorite: Boolean = false,
    val isCustom: Boolean = false,
    val addedAt: Long = System.currentTimeMillis()
)
