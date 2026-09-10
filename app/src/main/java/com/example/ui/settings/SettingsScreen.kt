package com.example.ui.settings

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.R
import com.example.ui.components.PlayerTopBar
import com.example.ui.components.visualScreenBackground
import com.example.ui.theme.*

@Composable
fun SettingsScreen(
    selectedTheme: String = ActiveThemeName,
    onThemeSelected: (String) -> Unit = {},
    onResetChannels: () -> Unit,
    onClearCache: () -> Unit,
    onNavigateToChannels: () -> Unit = {}
) {
    var hwAcceleration by remember { mutableStateOf(true) }
    var autoDetect by remember { mutableStateOf(true) }
    var bufferSizeSec by remember { mutableStateOf("15") }
    var customUserAgent by remember { mutableStateOf("YouseifPlayer/2.0 (Linux; Android)") }
    var selectedRatio by remember { mutableStateOf("16:9") }
    var showTheme by remember { mutableStateOf(false) }
    var showPlayback by remember { mutableStateOf(false) }
    var showSubtitle by remember { mutableStateOf(false) }
    var showUa by remember { mutableStateOf(false) }
    var showRatio by remember { mutableStateOf(false) }
    var showReset by remember { mutableStateOf(false) }
    var cleared by remember { mutableStateOf(false) }

    Box(Modifier.fillMaxSize().visualScreenBackground()) {
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(horizontal = 20.dp),
            contentPadding = PaddingValues(bottom = 96.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp)
        ) {
            item { PlayerTopBar() }
            item {
                Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text("SETTINGS", color = TextPrimary, fontSize = 28.sp, fontWeight = FontWeight.Black)
                    Text("App appearance and playback", color = TextMuted, fontSize = 12.sp)
                }
            }
            item {
                SettingsVisualRow(R.drawable.ui_theme_3d, "Colors & Appearance", "Presets · custom color · icons · font") { showTheme = true }
            }
            item {
                SettingsVisualRow(R.drawable.ui_download_3d, "استرداد قنوات / إضافة قائمة", "From URL or from file (.m3u / .m3u8 / .txt)") { onNavigateToChannels() }
            }
            item {
                SettingsVisualRow(R.drawable.ui_playback_3d, "Playback Settings", "Speed, autoplay and controls") { showPlayback = true }
            }
            item {
                SettingsVisualRow(R.drawable.ui_subtitle_3d, "Subtitle Settings", "Captions and appearance") { showSubtitle = true }
            }
            item {
                SettingsVisualRow(R.drawable.ui_restore_3d, "Restore Defaults", "Restore colors, icons and font") {
                    onThemeSelected("PURPLE")
                }
            }
            item {
                SettingsVisualRow(R.drawable.ui_clear_3d, "Clear Local Data", if (cleared) "Saved history and preferences cleared" else "Remove saved playlists and preferences") {
                    onClearCache(); cleared = true
                }
            }
            item {
                SettingsVisualRow(R.drawable.info, "About", "Youseif Player Pro") { }
            }
        }
    }

    if (showTheme) {
        VisualSheet("Colors & Appearance", onClose = { showTheme = false }) {
            Text("Theme / custom color applies to buttons AND player icons — icons follow the accent automatically", color = TextSecondary, fontSize = 12.sp)
            Spacer(Modifier.height(14.dp))
            val themes = listOf("PURPLE" to Color(0xFFC83DFF), "RED" to Color(0xFFFF3150), "GREEN" to Color(0xFF32E58A), "CYAN" to Color(0xFF20D9FF), "NEON PURPLE" to Color(0xFFA84CFF), "EMERALD" to Color(0xFF21D99A), "ICE" to Color(0xFF8ED5FF), "GOLD" to Color(0xFFFFC83D))
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                themes.chunked(3).forEach { row ->
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        row.forEach { (name, color) ->
                            val selected = selectedTheme == name
                            Box(Modifier.weight(1f).height(82.dp).clip(RoundedCornerShape(16.dp)).background(DarkSurface).border(1.dp, if (selected) color else CrimsonBorder, RoundedCornerShape(16.dp)).clickable { onThemeSelected(name); showTheme = false }, contentAlignment = Alignment.Center) {
                                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                    Box(Modifier.size(30.dp).clip(CircleShape).background(color))
                                    Spacer(Modifier.height(6.dp))
                                    Text(name.replace("NEON ", ""), color = TextPrimary, fontSize = 9.sp, fontWeight = FontWeight.SemiBold)
                                }
                            }
                        }
                        repeat(3 - row.size) { Spacer(Modifier.weight(1f)) }
                    }
                }
            }
            Spacer(Modifier.height(12.dp))
            Text("Icon style", color = TextPrimary, fontSize = 13.sp)
            Text("3D icons are kept for app chrome; the stable player controls remain unchanged.", color = TextMuted, fontSize = 10.sp)
            Spacer(Modifier.height(8.dp))
            Button(onClick = { showTheme = false }, modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(14.dp), colors = ButtonDefaults.buttonColors(containerColor = NeonRed)) { Text("Apply", fontWeight = FontWeight.Bold) }
        }
    }

    if (showPlayback) {
        VisualSheet("Playback Settings", onClose = { showPlayback = false }) {
            SettingToggle("Hardware Acceleration", hwAcceleration) { hwAcceleration = it }
            SettingToggle("Smart Auto-Detection", autoDetect) { autoDetect = it }
            SheetValueRow("Default aspect ratio", selectedRatio) { showRatio = true; showPlayback = false }
            SheetValueRow("Buffer duration", "$bufferSizeSec seconds") { bufferSizeSec = if (bufferSizeSec == "15") "30" else if (bufferSizeSec == "30") "5" else "15" }
            Button(onClick = { showPlayback = false }, modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(14.dp), colors = ButtonDefaults.buttonColors(containerColor = NeonRed)) { Text("Save") }
        }
    }

    if (showSubtitle) {
        VisualSheet("Subtitle Settings", onClose = { showSubtitle = false }) {
            SettingToggle("Enable CC", true) { }
            SheetValueRow("Font size", "Medium") { }
            SheetValueRow("Text color", "White") { }
            SheetValueRow("Timing delay", "0s (synced)") { }
            SheetValueRow("File encoding", "UTF-8") { }
            Button(onClick = { showSubtitle = false }, modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(14.dp), colors = ButtonDefaults.buttonColors(containerColor = NeonRed)) { Text("Save") }
        }
    }

    if (showUa) {
        AlertDialog(onDismissRequest = { showUa = false }, title = { Text("Custom User-Agent") }, text = { OutlinedTextField(customUserAgent, { customUserAgent = it }, singleLine = true) }, confirmButton = { TextButton({ showUa = false }) { Text("Save") } })
    }
    if (showRatio) {
        AlertDialog(onDismissRequest = { showRatio = false }, title = { Text("Select Aspect Ratio") }, text = { Column { listOf("16:9", "4:3", "Fit", "Fill / Zoom", "Original").forEach { r -> Row(Modifier.fillMaxWidth().clickable { selectedRatio = r; showRatio = false }.padding(12.dp), Arrangement.SpaceBetween) { Text(r); if (r == selectedRatio) Icon(Icons.Default.Check, null, tint = NeonRed) } } } }, confirmButton = {})
    }
    if (showReset) {
        AlertDialog(onDismissRequest = { showReset = false }, title = { Text("Restore Defaults?") }, text = { Text("Restore the visual defaults and clear built-in demo rows while keeping imported playlists.") }, confirmButton = { TextButton({ onResetChannels(); onThemeSelected("PURPLE"); showReset = false }) { Text("Restore") } }, dismissButton = { TextButton({ showReset = false }) { Text("Cancel") } })
    }
}

@Composable
private fun SettingsVisualRow(icon: Int, title: String, subtitle: String, onClick: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().height(138.dp).clip(RoundedCornerShape(24.dp))
            .background(Brush.horizontalGradient(listOf(NeonRedContainer.copy(alpha=.38f), DarkSurface.copy(alpha=.78f), TechCyan.copy(alpha=.08f))))
            .border(1.dp, CrimsonBorder.copy(alpha=.72f), RoundedCornerShape(24.dp)).clickable(onClick = onClick).padding(horizontal = 28.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(Modifier.size(80.dp).clip(RoundedCornerShape(22.dp)).background(NeonRedContainer.copy(alpha=.30f)).border(1.dp, NeonRed.copy(alpha=.35f), RoundedCornerShape(22.dp)), contentAlignment = Alignment.Center) {
            Image(painterResource(icon), null, Modifier.size(42.dp))
        }
        Spacer(Modifier.width(26.dp))
        Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Text(title, color = TextPrimary, fontSize = 17.sp, fontWeight = FontWeight.Bold)
            Text(subtitle, color = TextMuted, fontSize = 11.sp)
        }
    }
}

@Composable
private fun VisualSheet(title: String, onClose: () -> Unit, content: @Composable ColumnScope.() -> Unit) {
    Box(Modifier.fillMaxSize().background(Color.Black.copy(alpha=.60f)).clickable { onClose() }, contentAlignment = Alignment.BottomCenter) {
        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(24.dp,24.dp,0.dp,0.dp)).background(DarkCardBg).padding(18.dp).clickable { }) {
            Row(Modifier.fillMaxWidth(), Arrangement.SpaceBetween, Alignment.CenterVertically) { Text(title, color = TextPrimary, fontSize = 18.sp, fontWeight = FontWeight.Bold); TextButton(onClick = onClose) { Text("✕", color = TextPrimary, fontSize = 18.sp) } }
            content()
        }
    }
}

@Composable private fun SettingToggle(title: String, checked: Boolean, onChange: (Boolean) -> Unit) { Row(Modifier.fillMaxWidth().padding(vertical=8.dp), Arrangement.SpaceBetween, Alignment.CenterVertically) { Text(title, color=TextPrimary, fontSize=13.sp); Switch(checked,onChange) } }
@Composable private fun SheetValueRow(title: String, value: String, onClick: () -> Unit) { Row(Modifier.fillMaxWidth().clickable(onClick=onClick).padding(vertical=10.dp), Arrangement.SpaceBetween, Alignment.CenterVertically) { Text(title,color=TextPrimary,fontSize=13.sp); Text(value,color=NeonRedGlow,fontSize=12.sp) } }
