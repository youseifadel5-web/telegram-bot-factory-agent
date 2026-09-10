package com.example.ui.components

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.IconButton
import androidx.compose.material3.Icon
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Menu
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.material3.Text
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.R
import com.example.ui.theme.AmoledBlack
import com.example.ui.theme.CrimsonBorder
import com.example.ui.theme.DarkSurface
import com.example.ui.theme.NeonRed
import com.example.ui.theme.NeonRedGlow
import com.example.ui.theme.NeonRedContainer
import com.example.ui.theme.TechCyan
import com.example.ui.theme.TextMuted

@Composable
fun PlayerTopBar(
    modifier: Modifier = Modifier,
    onMenu: (() -> Unit)? = null,
    onRefresh: (() -> Unit)? = null,
    onInfo: (() -> Unit)? = null,
    title: String = "youseif",
    subtitle: String = "player pro"
) {
    Row(
        modifier = modifier.fillMaxWidth().height(112.dp).padding(horizontal = 18.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        ChromeMenuButton(onMenu)
        Spacer(Modifier.weight(1f))
        Box(contentAlignment = Alignment.Center) {
            Text(
                title,
                color = NeonRedGlow,
                fontSize = 31.sp,
                fontFamily = FontFamily.Serif,
                fontStyle = FontStyle.Italic,
                fontWeight = FontWeight.Bold,
                letterSpacing = .2.sp
            )
            Text(
                subtitle,
                color = TextMuted,
                fontSize = 10.sp,
                fontWeight = FontWeight.SemiBold,
                letterSpacing = 1.8.sp,
                modifier = Modifier.padding(top = 39.dp)
            )
        }
        Spacer(Modifier.weight(1f))
        Row(horizontalArrangement = Arrangement.spacedBy(5.dp)) {
            ChromeIconButton(R.drawable.refresh, "Refresh", onRefresh, 48.dp, 23.dp)
            ChromeIconButton(R.drawable.info, "Info", onInfo, 48.dp, 23.dp)
        }
    }
}


@Composable
private fun ChromeMenuButton(onClick: (() -> Unit)?) {
    IconButton(
        onClick = { onClick?.invoke() },
        enabled = onClick != null,
        modifier = Modifier.size(48.dp).shadow(12.dp, RoundedCornerShape(18.dp), ambientColor = NeonRed.copy(alpha=.28f), spotColor = NeonRedGlow.copy(alpha=.5f)).clip(RoundedCornerShape(18.dp))
            .background(Brush.linearGradient(listOf(NeonRedContainer.copy(alpha=.42f), DarkSurface.copy(alpha=.86f), TechCyan.copy(alpha=.06f))))
            .border(1.dp, CrimsonBorder.copy(alpha=.95f), RoundedCornerShape(18.dp))
    ) {
        Icon(Icons.Default.Menu, contentDescription = "Menu", tint = NeonRedGlow, modifier = Modifier.size(29.dp))
    }
}
@Composable
private fun ChromeIconButton(iconRes: Int, description: String, onClick: (() -> Unit)?, size: androidx.compose.ui.unit.Dp, iconSize: androidx.compose.ui.unit.Dp) {
    IconButton(
        onClick = { onClick?.invoke() },
        enabled = onClick != null,
        modifier = Modifier
            .size(size)
            .shadow(12.dp, RoundedCornerShape(18.dp), ambientColor = NeonRed.copy(alpha=.28f), spotColor = NeonRedGlow.copy(alpha=.5f))
            .clip(RoundedCornerShape(18.dp))
            .background(Brush.linearGradient(listOf(NeonRedContainer.copy(alpha=.42f), DarkSurface.copy(alpha=.86f), TechCyan.copy(alpha=.06f))))
            .border(1.dp, CrimsonBorder.copy(alpha=.95f), RoundedCornerShape(18.dp))
    ) {
        Image(painterResource(iconRes), description, modifier = Modifier.size(iconSize))
    }
}

fun Modifier.visualScreenBackground(): Modifier = this.background(
    Brush.verticalGradient(
        listOf(
            Color(0xFF080316),
            Color(0xFF281047),
            Color(0xFF09253A),
            AmoledBlack
        )
    )
)

fun Modifier.glassPanel(radius: Int = 22): Modifier = this
    .clip(RoundedCornerShape(radius.dp))
    .background(Brush.horizontalGradient(listOf(NeonRedContainer.copy(alpha=.28f), DarkSurface.copy(alpha=.74f), TechCyan.copy(alpha=.10f))))
    .border(1.dp, CrimsonBorder.copy(alpha=.8f), RoundedCornerShape(radius.dp))
