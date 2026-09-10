package com.example.ui.components

import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.ui.theme.AmoledBlack
import com.example.ui.theme.CrimsonBorder
import com.example.ui.theme.DarkCardBg
import com.example.ui.theme.DarkSurface
import com.example.ui.theme.LiveGreen
import com.example.ui.theme.LiveRed
import com.example.ui.theme.NeonRed
import com.example.ui.theme.NeonRedContainer
import com.example.ui.theme.NeonRedGlow
import com.example.ui.theme.SignalGreen
import com.example.ui.theme.SignalOrange
import com.example.ui.theme.SignalYellow
import com.example.ui.theme.TechCyan
import com.example.ui.theme.TextPrimary
import com.example.ui.theme.TextSecondary

fun Modifier.neonCard(
    shape: Shape = RoundedCornerShape(10.dp),
    borderColor: Color = CrimsonBorder,
    borderWidth: Float = 1f
): Modifier = this
    .clip(shape)
    .background(DarkCardBg)
    .border(borderWidth.dp, borderColor, shape)

fun Modifier.neonGlowCard(
    shape: Shape = RoundedCornerShape(12.dp)
): Modifier = this
    .shadow(6.dp, shape, ambientColor = NeonRed.copy(alpha = 0.3f), spotColor = NeonRedGlow.copy(alpha = 0.6f))
    .clip(shape)
    .background(DarkCardBg)
    .border(1.2.dp, Brush.linearGradient(listOf(NeonRedGlow, CrimsonBorder, DarkCardBg)), shape)

@Composable
fun LiveBadge(
    modifier: Modifier = Modifier,
    isLive: Boolean = true,
    text: String = if (isLive) "LIVE" else "VOD"
) {
    val infiniteTransition = rememberInfiniteTransition(label = "live_pulse")
    val alpha by infiniteTransition.animateFloat(
        initialValue = 0.4f,
        targetValue = 1.0f,
        animationSpec = infiniteRepeatable(
            animation = tween(650, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Reverse
        ),
        label = "live_alpha"
    )

    Row(
        modifier = modifier
            .clip(RoundedCornerShape(4.dp))
            .background(if (isLive) NeonRedContainer else DarkSurface)
            .border(0.8.dp, if (isLive) NeonRed.copy(alpha = 0.8f) else CrimsonBorder, RoundedCornerShape(4.dp))
            .padding(horizontal = 6.dp, vertical = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        if (isLive) {
            Box(
                modifier = Modifier
                    .size(6.dp)
                    .clip(CircleShape)
                    .background(LiveRed.copy(alpha = alpha))
            )
        }
        Text(
            text = text,
            color = if (isLive) TextPrimary else TechCyan,
            fontSize = 10.sp,
            fontWeight = FontWeight.Bold,
            letterSpacing = 0.5.sp
        )
    }
}

@Composable
fun SignalIndicator(
    bars: Int = 4,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier,
        horizontalArrangement = Arrangement.spacedBy(2.dp),
        verticalAlignment = Alignment.Bottom
    ) {
        val heights = listOf(4.dp, 7.dp, 10.dp, 13.dp)
        val color = when {
            bars >= 4 -> SignalGreen
            bars == 3 -> SignalGreen.copy(alpha = 0.9f)
            bars == 2 -> SignalYellow
            else -> SignalOrange
        }

        for (i in 0 until 4) {
            val barActive = i < bars
            Box(
                modifier = Modifier
                    .width(2.5.dp)
                    .height(heights[i])
                    .clip(RoundedCornerShape(1.dp))
                    .background(if (barActive) color else Color(0xFF2A2A30))
            )
        }
    }
}

@Composable
fun TechTag(
    text: String,
    modifier: Modifier = Modifier,
    color: Color = TechCyan
) {
    Box(
        modifier = modifier
            .clip(RoundedCornerShape(4.dp))
            .background(color.copy(alpha = 0.12f))
            .border(0.6.dp, color.copy(alpha = 0.4f), RoundedCornerShape(4.dp))
            .padding(horizontal = 5.dp, vertical = 1.5.dp)
    ) {
        Text(
            text = text,
            color = color,
            fontSize = 9.5.sp,
            fontWeight = FontWeight.SemiBold
        )
    }
}
