package com.example.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.player.StreamDiagnostics
import com.example.ui.theme.CrimsonBorder
import com.example.ui.theme.DarkCardBg
import com.example.ui.theme.LiveGreen
import com.example.ui.theme.NeonRed
import com.example.ui.theme.TextMuted
import com.example.ui.theme.TextPrimary
import com.example.ui.theme.TextSecondary

@Composable
fun DiagnosticDashboardCards(
    diagnostics: StreamDiagnostics,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 14.dp),
        horizontalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        // STREAM INFO CARD
        Box(
            modifier = Modifier
                .weight(1f)
                .clip(RoundedCornerShape(18.dp))
                .background(
                    Brush.horizontalGradient(
                        listOf(NeonRedContainer.copy(alpha = .22f), DarkCardBg.copy(alpha = .88f), TechCyan.copy(alpha = .08f))
                    )
                )
                .border(1.dp, CrimsonBorder.copy(alpha = .72f), RoundedCornerShape(18.dp))
                .padding(horizontal = 12.dp, vertical = 11.dp)
        ) {
            Column(
                verticalArrangement = Arrangement.spacedBy(5.dp)
            ) {
                // Header
                Text(
                    text = "STREAM INFO",
                    color = NeonRed,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Bold,
                    letterSpacing = 0.5.sp
                )

                Spacer(modifier = Modifier.height(2.dp))

                StreamDetailRow(label = "Protocol", value = diagnostics.protocol)
                StreamDetailRow(label = "Resolution", value = diagnostics.resolution)
                StreamDetailRow(label = "Codec", value = diagnostics.videoCodec)
                StreamDetailRow(label = "FPS", value = "${diagnostics.fps}")
                StreamDetailRow(label = "Bitrate", value = String.format("%.2f Mbps", diagnostics.downloadSpeedKbps / 1000f))
                StreamDetailRow(label = "Audio", value = diagnostics.audioCodec)

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "Status",
                        color = TextMuted,
                        fontSize = 11.sp
                    )
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(4.dp)
                    ) {
                        val status = when {
                            diagnostics.isPlaying && diagnostics.downloadSpeedKbps > 0 -> "Connected"
                            diagnostics.isPlaying || diagnostics.isLoading -> "Measuring"
                            else -> "Waiting"
                        }
                        Box(
                            modifier = Modifier
                                .size(6.dp)
                                .clip(CircleShape)
                                .background(if (status == "Connected") LiveGreen else TextMuted)
                        )
                        Text(
                            text = status,
                            color = if (status == "Connected") LiveGreen else TextMuted,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.Medium
                        )
                    }
                }
            }
        }

        // CONNECTION CARD WITH LIVE CHART
        Box(
            modifier = Modifier
                .weight(1f)
                .clip(RoundedCornerShape(18.dp))
                .background(
                    Brush.horizontalGradient(
                        listOf(NeonRedContainer.copy(alpha = .22f), DarkCardBg.copy(alpha = .88f), TechCyan.copy(alpha = .08f))
                    )
                )
                .border(1.dp, CrimsonBorder.copy(alpha = .72f), RoundedCornerShape(18.dp))
                .padding(horizontal = 12.dp, vertical = 11.dp)
        ) {
            Column(
                verticalArrangement = Arrangement.spacedBy(4.dp)
            ) {
                // Top Header Row: CONNECTION and 4.25 Mbps
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "CONNECTION",
                        color = NeonRed,
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Bold,
                        letterSpacing = 0.5.sp
                    )
                    Text(
                        text = String.format("%.2f Mbps", diagnostics.downloadSpeedKbps / 1000f),
                        color = NeonRed,
                        fontSize = 11.5.sp,
                        fontWeight = FontWeight.Bold
                    )
                }

                Text(
                    text = "Mbps",
                    color = TextMuted,
                    fontSize = 10.sp
                )

                // Live waveform chart
                ConnectionWaveformChart(
                    speedKbps = diagnostics.downloadSpeedKbps,
                    isConnected = diagnostics.isPlaying || diagnostics.isLoading,
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(84.dp)
                )

                Spacer(modifier = Modifier.height(2.dp))

                // Bottom row: real connection state and buffer
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(4.dp)
                    ) {
                        Box(
                            modifier = Modifier
                                .size(6.dp)
                                .clip(CircleShape)
                                .background(LiveGreen)
                        )
                        Text(
                            text = if (diagnostics.isPlaying && diagnostics.downloadSpeedKbps > 0) "LIVE" else if (diagnostics.isLoading) "MEASURING" else "IDLE",
                            color = if (diagnostics.isPlaying && diagnostics.downloadSpeedKbps > 0) LiveGreen else TextMuted,
                            fontSize = 10.sp,
                            fontWeight = FontWeight.Bold
                        )
                    }

                    Text(
                        text = "Buffer ${String.format("%.1f", diagnostics.bufferMs / 1000f)}s",
                        color = TextMuted,
                        fontSize = 10.sp
                    )
                }
            }
        }
    }
}

@Composable
private fun StreamDetailRow(
    label: String,
    value: String
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            text = label,
            color = TextMuted,
            fontSize = 11.sp
        )
        Text(
            text = value,
            color = TextPrimary,
            fontSize = 11.sp,
            fontWeight = FontWeight.Medium
        )
    }
}

@Composable
fun ConnectionWaveformChart(
    speedKbps: Long,
    isConnected: Boolean,
    modifier: Modifier = Modifier
) {
    // State-backed samples: every real Media3 bandwidth estimate triggers a redraw.
    // No random/fake network values are generated here.
    val samples = remember { mutableStateListOf<Float>() }
    val latestSpeedKbps by rememberUpdatedState(speedKbps)

    androidx.compose.runtime.LaunchedEffect(isConnected) {
        while (kotlinx.coroutines.currentCoroutineContext().isActive) {
            samples.add(latestSpeedKbps.coerceAtLeast(0L) / 1000f)
            if (samples.size > 32) samples.removeAt(0)
            kotlinx.coroutines.delay(600L)
        }
    }

    val samplePoints = if (samples.isEmpty()) listOf(0f) else samples.toList()
    val peak = maxOf(1f, (samplePoints.maxOrNull() ?: 1f) * 1.25f)
    val current = samplePoints.lastOrNull() ?: 0f

    Box(modifier = modifier) {
        Column(
            modifier = Modifier
                .fillMaxHeight()
                .padding(end = 4.dp),
            verticalArrangement = Arrangement.SpaceBetween
        ) {
            Text(String.format("%.1f", peak), color = TextMuted.copy(alpha = 0.55f), fontSize = 8.sp)
            Text(String.format("%.1f", peak * .66f), color = TextMuted.copy(alpha = 0.45f), fontSize = 8.sp)
            Text(String.format("%.1f", peak * .33f), color = TextMuted.copy(alpha = 0.45f), fontSize = 8.sp)
            Text("0", color = TextMuted.copy(alpha = 0.55f), fontSize = 8.sp)
        }

        Canvas(
            modifier = Modifier
                .fillMaxWidth()
                .fillMaxHeight()
                .padding(start = 20.dp, top = 4.dp, bottom = 4.dp)
        ) {
            val width = size.width
            val height = size.height
            val gridColor = Color(0x22FFFFFF)
            drawLine(gridColor, Offset(0f, 0f), Offset(width, 0f), strokeWidth = 1f)
            drawLine(gridColor, Offset(0f, height * .33f), Offset(width, height * .33f), strokeWidth = 1f)
            drawLine(gridColor, Offset(0f, height * .66f), Offset(width, height * .66f), strokeWidth = 1f)
            drawLine(gridColor, Offset(0f, height), Offset(width, height), strokeWidth = 1f)

            if (samplePoints.size >= 2) {
                val stepX = width / (samplePoints.size - 1).coerceAtLeast(1)
                val linePath = Path()
                val fillPath = Path()
                fillPath.moveTo(0f, height)

                samplePoints.forEachIndexed { index, value ->
                    val x = index * stepX
                    val normalized = (value / peak).coerceIn(0f, 1f)
                    val y = height - normalized * height
                    if (index == 0) {
                        linePath.moveTo(x, y)
                        fillPath.lineTo(x, y)
                    } else {
                        val prevX = (index - 1) * stepX
                        val prevY = height - (samplePoints[index - 1] / peak).coerceIn(0f, 1f) * height
                        val cx = (prevX + x) / 2f
                        linePath.cubicTo(cx, prevY, cx, y, x, y)
                        fillPath.cubicTo(cx, prevY, cx, y, x, y)
                    }
                }
                fillPath.lineTo(width, height)
                fillPath.close()

                drawPath(
                    path = fillPath,
                    brush = Brush.verticalGradient(
                        listOf(NeonRed.copy(alpha = .28f), NeonRed.copy(alpha = .02f), Color.Transparent)
                    )
                )
                drawPath(path = linePath, color = NeonRed.copy(alpha = .25f), style = Stroke(width = 5.dp.toPx()))
                drawPath(path = linePath, color = NeonRedGlow, style = Stroke(width = 1.8.dp.toPx()))

                val lastX = (samplePoints.lastIndex) * stepX
                val lastY = height - (current / peak).coerceIn(0f, 1f) * height
                drawCircle(NeonRedGlow.copy(alpha = .18f), radius = 7.dp.toPx(), center = Offset(lastX, lastY))
                drawCircle(NeonRedGlow, radius = 2.5.dp.toPx(), center = Offset(lastX, lastY))
            } else if (isConnected) {
                val y = height * .55f
                drawLine(NeonRedGlow.copy(alpha = .5f), Offset(0f, y), Offset(width, y), strokeWidth = 2.dp.toPx())
            }
        }
    }
}
