package com.example.data

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "history")
data class HistoryItem(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    val title: String,
    val url: String,
    val group: String = "LIVE",
    val logoUrl: String = "",
    val playedAt: Long = System.currentTimeMillis(),
    val durationMs: Long = 0L,
    val positionMs: Long = 0L
)
