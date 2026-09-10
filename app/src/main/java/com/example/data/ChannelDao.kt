package com.example.data

import androidx.room.Dao
import androidx.room.Delete
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Update
import kotlinx.coroutines.flow.Flow

@Dao
interface ChannelDao {
    @Query("SELECT * FROM channels ORDER BY channelNumber ASC, name ASC")
    fun getAllChannels(): Flow<List<PlaylistItem>>

    @Query("SELECT * FROM channels WHERE isFavorite = 1 ORDER BY channelNumber ASC")
    fun getFavoriteChannels(): Flow<List<PlaylistItem>>

    @Query("SELECT * FROM channels WHERE `group` = :group ORDER BY channelNumber ASC")
    fun getChannelsByGroup(group: String): Flow<List<PlaylistItem>>

    @Query("SELECT DISTINCT `group` FROM channels WHERE `group` != '' ORDER BY `group` ASC")
    fun getAllGroups(): Flow<List<String>>

    @Query("SELECT * FROM channels WHERE id = :id LIMIT 1")
    suspend fun getChannelById(id: String): PlaylistItem?

    @Query("SELECT * FROM channels WHERE url = :url LIMIT 1")
    suspend fun getChannelByUrl(url: String): PlaylistItem?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertChannels(channels: List<PlaylistItem>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertChannel(channel: PlaylistItem)

    @Update
    suspend fun updateChannel(channel: PlaylistItem)

    @Query("UPDATE channels SET isFavorite = :isFavorite WHERE id = :id")
    suspend fun setFavorite(id: String, isFavorite: Boolean)

    @Delete
    suspend fun deleteChannel(channel: PlaylistItem)

    @Query("DELETE FROM channels WHERE isCustom = 1")
    suspend fun clearCustomChannels()

    @Query("DELETE FROM channels WHERE isCustom = 0")
    suspend fun clearBuiltInChannels()

    @Query("DELETE FROM channels")
    suspend fun clearAll()
}
