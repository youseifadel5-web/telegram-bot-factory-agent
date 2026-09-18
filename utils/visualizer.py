"""Animated live panel for Youseif streams."""
import html

COLORS = ["🟥", "🟧", "🟨", "🟩", "🟦", "🟪"]
SYMBOL_FRAMES = [
    "◆◇◆◇◆◇◆◇◆◇",
    "◇◆◇◆◇◆◇◆◇◆",
    "◆◆◇◇◆◆◇◇◆◆",
    "◇◇◆◆◇◇◆◆◇◇",
    "⬡⬢⬡⬢⬡⬢⬡⬢⬡⬢",
    "⬢⬡⬢⬡⬢⬡⬢⬡⬢⬡",
    "◉◎◉◎◉◎◉◎◉◎",
    "◎◉◎◉◎◉◎◉◎◉",
]
SPECTRUM = ["🔹", "🔸", "▪️", "🔸", "🔹", "🔸", "▪️", "🔹"]
WHITE = "⬜"


def _loading_bar(tick: int, width: int = 10) -> str:
    """Moving colored wave left-right then reverse."""
    cycle = width * 2
    pos = tick % cycle
    if pos >= width:
        pos = cycle - pos
    # 3-cell wide color blob
    cells = []
    for i in range(width):
        dist = abs(i - pos)
        if dist == 0:
            cells.append(COLORS[tick % len(COLORS)])
        elif dist == 1:
            cells.append(COLORS[(tick + 2) % len(COLORS)])
        elif dist == 2:
            cells.append(COLORS[(tick + 4) % len(COLORS)])
        else:
            cells.append(WHITE)
    pct = int(10 + (tick * 7) % 90)
    return "".join(cells) + f" {pct}%"


def _spectrum(tick: int) -> str:
    n = len(SPECTRUM)
    return "".join(SPECTRUM[(tick + i) % n] for i in range(8))


def _signal_dots(tick: int) -> str:
    order = ["🟢", "🔵", "🟣", "🟡", "🟠", "🔴"]
    return "".join(order[(tick + i) % len(order)] for i in range(6))


def glow_name(tick: int = 0) -> str:
    s = ["💫 <b>Youseif</b> 💫", "✨ <b>Youseif</b> ✨", "⚡ <b>Youseif</b> ⚡", "🌟 <b>Youseif</b> 🌟"]
    return s[tick % len(s)]


def state_label(state: str) -> str:
    return {
        "on_air": "🟢 <b>ON AIR</b> · بث مستقر",
        "connecting": "🟡 <b>جاري الاتصال...</b>",
        "reconnecting": "🟡 <b>جاري إعادة الاتصال...</b>",
        "error": "🔴 <b>خطأ في البث</b>",
        "stopped": "🔴 <b>البث متوقف</b>",
    }.get(state, "🔴 <b>البث متوقف</b>")


def vol_bar(volume: float) -> str:
    # volume 0.0 - 2.0 → 0-100 display scaled to 1.0 = 100%
    pct = int(min(100, max(0, volume * 100)))
    filled = pct // 10
    return "🟩" * filled + "⬜" * (10 - filled) + f" {pct}%"


def build_live_panel(
    title: str,
    stream_id: int,
    running: bool,
    uptime: str,
    tick: int = 0,
    state: str = None,
    volume: float = 1.0,
    bitrate: str = "128k",
    restarts: int = 0,
    last_error: str = "",
    ffmpeg_ok: bool = True,
    rtmp_ok: bool = True,
    source_ok: bool = True,
    codec_info: str = "AAC 128k · 48kHz Stereo",
    quality: str = "متوسط",
) -> str:
    safe_title = html.escape(str(title)[:40])
    if state is None:
        state = "on_air" if running else "stopped"
    sym = SYMBOL_FRAMES[tick % len(SYMBOL_FRAMES)]
    bar = _loading_bar(tick)
    spec = _spectrum(tick)
    sig = _signal_dots(tick)

    def _st(ok: bool, label: str) -> str:
        return f"{'🟢' if ok else '🔴'} {label}"

    err_line = ""
    if last_error and state in ("error", "reconnecting", "stopped", "connecting"):
        err_line = f"\n⚠️ Debug:\n<code>{html.escape(str(last_error)[:220])}</code>"

    return (
        f"{glow_name(tick)}\n\n"
        f"{sym}\n"
        f"{bar}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>{safe_title}</b>\n"
        f"🆔 Stream <code>#{stream_id}</code>\n"
        f"{state_label(state)}\n"
        f"{spec}\n"
        f"⏱ مدة التشغيل: <code>{uptime}</code>"
        f"{' · ♻️ ' + str(restarts) if restarts else ''}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔊 مستوى الصوت:\n{vol_bar(volume)}\n"
        f"🎚 الجودة: <b>{html.escape(quality)}</b>\n"
        f"🎵 الترميز: <code>{html.escape(codec_info or bitrate)}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📡 حالة الاتصال:\n"
        f"{_st(ffmpeg_ok, 'FFmpeg')}  ·  {_st(rtmp_ok, 'RTMP')}  ·  {_st(source_ok, 'المصدر')}\n"
        f"📶 قوة الإشارة:\n{sig}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{sym}\n"
        f"{bar}\n\n"
        f"📡 البث المستمر على القناة"
        f"{err_line}"
    )
