package com.example

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import com.example.data.DefaultChannels
import com.example.data.M3UParser
import com.example.player.StreamResolver
import com.example.player.StreamType
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class ExampleRobolectricTest {

    @Test
    fun `read app name string from context`() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val appName = context.getString(R.string.app_name)
        assertEquals("YouseifPlayer", appName)
    }

    @Test
    fun `test default channels populated`() {
        assertTrue(DefaultChannels.CHANNELS.isNotEmpty())
        assertEquals(1, DefaultChannels.CHANNELS.first().channelNumber)
    }

    @Test
    fun `test m3u parser and exporter`() {
        val m3uSample = """
            #EXTM3U
            #EXTINF:-1 tvg-id="beinsports1" tvg-name="beIN 1" tvg-logo="https://example.com/logo.png" group-title="SPORTS",beIN Sports 1 Premium
            https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8
        """.trimIndent()

        val parsed = M3UParser.parse(m3uSample)
        assertEquals(1, parsed.size)
        assertEquals("beIN Sports 1 Premium", parsed[0].name)
        assertEquals("SPORTS", parsed[0].group)
        assertEquals("https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8", parsed[0].url)

        val exported = M3UParser.exportToM3U(parsed)
        assertTrue(exported.contains("#EXTM3U"))
        assertTrue(exported.contains("beIN Sports 1 Premium"))
    }

    @Test
    fun `test pixeldrain direct file stream resolution`() = runBlocking {
        val resolved = StreamResolver.resolve("https://pixeldrain.com/api/file/weTom3Pa")
        assertEquals(StreamType.PROGRESSIVE, resolved.type)
        assertEquals("https://pixeldrain.com/api/file/weTom3Pa", resolved.url)

        val resolved2 = StreamResolver.resolve("https://pixeldrain.com/u/weTom3Pa")
        assertEquals(StreamType.PROGRESSIVE, resolved2.type)
        assertEquals("https://pixeldrain.com/api/file/weTom3Pa", resolved2.url)
    }
}
