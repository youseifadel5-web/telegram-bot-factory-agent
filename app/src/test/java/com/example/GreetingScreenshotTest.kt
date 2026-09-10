package com.example

import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onRoot
import com.example.player.StreamDiagnostics
import com.example.ui.components.DiagnosticDashboardCards
import com.example.ui.theme.AmoledBlack
import com.example.ui.theme.MyApplicationTheme
import com.github.takahirom.roborazzi.RobolectricDeviceQualifiers
import com.github.takahirom.roborazzi.captureRoboImage
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(qualifiers = RobolectricDeviceQualifiers.Pixel8, sdk = [34])
class GreetingScreenshotTest {

    @get:Rule
    val composeTestRule = createComposeRule()

    @Test
    fun player_cards_screenshot() {
        composeTestRule.setContent {
            MyApplicationTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = AmoledBlack
                ) {
                    val sampleDiagnostics = StreamDiagnostics(
                        isPlaying = true,
                        resolution = "1920x1080",
                        fps = 60,
                        videoCodec = "H.264 / AVC",
                        audioCodec = "AAC Stereo (48kHz)",
                        bitrateKbps = 4500L,
                        bufferMs = 3200L,
                        bufferPercentage = 85,
                        protocol = "HTTPS (HLS)",
                        latencyMs = 42L,
                        downloadSpeedKbps = 18500L
                    )
                    DiagnosticDashboardCards(diagnostics = sampleDiagnostics)
                }
            }
        }

        composeTestRule.onRoot().captureRoboImage(filePath = "src/test/screenshots/stream_info_card.png")
    }
}
