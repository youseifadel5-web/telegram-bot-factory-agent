package com.example.ui.theme

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.graphics.Color

data class PlayerPalette(
    val background: Color,
    val surface: Color,
    val surfaceVariant: Color,
    val card: Color,
    val border: Color,
    val accent: Color,
    val accentGlow: Color,
    val accentDark: Color,
    val accentContainer: Color,
    val secondary: Color,
    val text: Color,
    val secondaryText: Color,
    val muted: Color
)

private val palettes = mapOf(
    "PURPLE" to PlayerPalette(Color(0xFF03030A), Color(0xFF0B0A14), Color(0xFF141126), Color(0xFF101020), Color(0xFF3B1B62), Color(0xFFC83DFF), Color(0xFFE56BFF), Color(0xFF7020A0), Color(0xFF34105A), Color(0xFF32D8FF), Color.White, Color(0xFFC7C4D4), Color(0xFF777286)),
    "RED" to PlayerPalette(Color(0xFF050204), Color(0xFF12070A), Color(0xFF210D12), Color(0xFF17090D), Color(0xFF5A1720), Color(0xFFFF3150), Color(0xFFFF667C), Color(0xFF9B1028), Color(0xFF420D18), Color(0xFFFF8A9B), Color.White, Color(0xFFD7C4C9), Color(0xFF81727A)),
    "GREEN" to PlayerPalette(Color(0xFF020805), Color(0xFF08150E), Color(0xFF102419), Color(0xFF0C1A12), Color(0xFF1B5635), Color(0xFF32E58A), Color(0xFF7BFFB6), Color(0xFF16804B), Color(0xFF0B4428), Color(0xFF5DE7FF), Color.White, Color(0xFFC5D8CC), Color(0xFF708379)),
    "CYAN" to PlayerPalette(Color(0xFF02070B), Color(0xFF07131A), Color(0xFF0B202A), Color(0xFF0A171F), Color(0xFF164A5B), Color(0xFF20D9FF), Color(0xFF70E9FF), Color(0xFF087A95), Color(0xFF073A4A), Color(0xFF8B7CFF), Color.White, Color(0xFFC1D8DE), Color(0xFF718B93)),
    "NEON PURPLE" to PlayerPalette(Color(0xFF04020B), Color(0xFF100A1C), Color(0xFF1D1030), Color(0xFF150C24), Color(0xFF52237A), Color(0xFFA84CFF), Color(0xFFD17BFF), Color(0xFF6921A0), Color(0xFF321050), Color(0xFF4CDFFF), Color.White, Color(0xFFD0C4DD), Color(0xFF80738D)),
    "EMERALD" to PlayerPalette(Color(0xFF020806), Color(0xFF071711), Color(0xFF0D261C), Color(0xFF0A1C14), Color(0xFF1B5A42), Color(0xFF21D99A), Color(0xFF70FFC3), Color(0xFF0D855C), Color(0xFF0B4A35), Color(0xFF58DFFF), Color.White, Color(0xFFC5DDD3), Color(0xFF708A7E)),
    "ICE" to PlayerPalette(Color(0xFF02070D), Color(0xFF08131D), Color(0xFF0E2230), Color(0xFF0B1822), Color(0xFF27536B), Color(0xFF8ED5FF), Color(0xFFC4ECFF), Color(0xFF3B7FA4), Color(0xFF123D56), Color(0xFF8C7CFF), Color.White, Color(0xFFC7DDE8), Color(0xFF728A96)),
    "GOLD" to PlayerPalette(Color(0xFF080603), Color(0xFF151108), Color(0xFF241D0E), Color(0xFF19140A), Color(0xFF5B4715), Color(0xFFFFC83D), Color(0xFFFFE28A), Color(0xFF9A6F10), Color(0xFF49340A), Color(0xFFFF8A4C), Color.White, Color(0xFFE0D4BA), Color(0xFF8A7D64))
)
private var activePalette by mutableStateOf(palettes.getValue("PURPLE"))
var ActiveThemeName: String by mutableStateOf("PURPLE")
    private set

// Global Compose state keeps the existing UI screens compatible while allowing every screen to react to theme changes.
var AmoledBlack: Color by mutableStateOf(activePalette.background)
var DarkSurface: Color by mutableStateOf(activePalette.surface)
var DarkSurfaceVariant: Color by mutableStateOf(activePalette.surfaceVariant)
var DarkCardBg: Color by mutableStateOf(activePalette.card)
var DarkCardBorder: Color by mutableStateOf(activePalette.border)
var NeonRed: Color by mutableStateOf(activePalette.accent)
var NeonRedGlow: Color by mutableStateOf(activePalette.accentGlow)
var NeonRedDark: Color by mutableStateOf(activePalette.accentDark)
var CrimsonBorder: Color by mutableStateOf(activePalette.border)
var NeonRedContainer: Color by mutableStateOf(activePalette.accentContainer)
var TechCyan: Color by mutableStateOf(activePalette.secondary)
var TextPrimary: Color by mutableStateOf(activePalette.text)
var TextSecondary: Color by mutableStateOf(activePalette.secondaryText)
var TextMuted: Color by mutableStateOf(activePalette.muted)

val LiveGreen = Color(0xFF00E676)
val LiveRed = Color(0xFFFF1744)
val SignalGreen = Color(0xFF00E676)
val SignalYellow = Color(0xFFFFD600)
val SignalOrange = Color(0xFFFF9100)
val TechGold = Color(0xFFFFC107)
val TextRed = Color(0xFFFF4D4D)

fun applyPlayerTheme(name: String) {
    val key = name.uppercase().ifBlank { "PURPLE" }
    val p = palettes[key] ?: palettes.getValue("PURPLE")
    activePalette = p
    ActiveThemeName = if (palettes.containsKey(key)) key else "PURPLE"
    AmoledBlack = p.background
    DarkSurface = p.surface
    DarkSurfaceVariant = p.surfaceVariant
    DarkCardBg = p.card
    DarkCardBorder = p.border
    NeonRed = p.accent
    NeonRedGlow = p.accentGlow
    NeonRedDark = p.accentDark
    CrimsonBorder = p.border
    NeonRedContainer = p.accentContainer
    TechCyan = p.secondary
    TextPrimary = p.text
    TextSecondary = p.secondaryText
    TextMuted = p.muted
}

fun availablePlayerThemes(): List<String> = palettes.keys.toList()
