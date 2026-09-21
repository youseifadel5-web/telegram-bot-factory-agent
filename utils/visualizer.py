"""Truthful live stream status panel.

This module intentionally avoids animated/fake percentages and signal meters.
All metrics shown are taken from StreamManager/FFmpeg metadata.
"""
from __future__ import annotations
import html


def state_label(state: str) -> str:
    return {
        "on_air": "🟢 <b>ON AIR</b> · تدفق مؤكد",
        "running": "🟢 <b>يعمل</b> · تدفق مؤكد",
        "connecting": "🟡 <b>جاري الاتصال...</b>",
        "reconnecting": "🟠 <b>جاري إعادة الاتصال...</b>",
        "restarting": "🟠 <b>جاري إعادة التشغيل...</b>",
        "stalled": "🟠 <b>التدفق متوقف مؤقتًا</b>",
        "failed": "🔴 <b>فشل البث</b>",
        "error": "🔴 <b>خطأ في البث</b>",
        "stopped": "🔴 <b>البث متوقف</b>",
    }.get(state or "stopped", "🔴 <b>البث متوقف</b>")


def _fmt_bitrate(value: str) -> str:
    if not value or value in ("N/A", "unknown"):
        return "غير متاح"
    return str(value)


def _fmt_progress(meta: dict) -> str:
    p = meta.get("progress") or {}
    br = p.get("bitrate_str") or meta.get("bitrate") or ""
    speed = p.get("speed_str") or meta.get("speed") or ""
    return _fmt_bitrate(br), (str(speed) if speed else "غير متاح")


def _codec_info(meta: dict) -> str:
    if meta.get("codec_info"):
        return str(meta["codec_info"])
    ac = meta.get("audio_codec") or "AAC"
    ab = meta.get("audio_bitrate") or "128k"
    sr = meta.get("sample_rate") or "48kHz"
    ch = meta.get("channels") or "Stereo"
    return f"{ac} {ab} · {sr} {ch}"


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
    quality: str = "غير متاح",
    meta: dict | None = None,
) -> str:
    meta = meta or {}
    safe_title = html.escape(str(title)[:60])
    state = state or ("on_air" if running else "stopped")
    media_kind = str(meta.get("media_kind") or "unknown").lower()
    has_video = meta.get("has_video")
    has_audio = meta.get("has_audio")
    if media_kind == "audio" or (has_audio and has_video is False):
        media_line = "🎵 النوع: <b>Audio فقط</b>"
    elif has_video is False:
        media_line = "🎵 النوع: <b>Audio فقط</b>"
    else:
        media_line = "🎥 النوع: <b>Video</b>"

    real_br, speed = _fmt_progress(meta)
    resolution = meta.get("resolution") or quality or "غير متاح"
    fps = meta.get("fps") or "غير متاح"
    source_type = meta.get("source_type") or "غير متاح"
    pid = meta.get("pid") or "غير متاح"
    reconnects = meta.get("reconnect_count", meta.get("restarts", restarts))
    frames = (meta.get("progress") or {}).get("frame")
    frames_text = str(frames) if frames is not None else "غير متاح"
    data_flow = bool(meta.get("data_flow"))
    stalled = state in ("stalled", "reconnecting", "restarting") and running and not data_flow

    def st(ok: bool, label: str) -> str:
        return f"{'🟢' if ok else '🔴'} {label}"

    err_line = ""
    if last_error and state in ("failed", "error", "reconnecting", "restarting", "stalled", "stopped"):
        err_line = f"\n⚠️ <b>آخر خطأ:</b> <code>{html.escape(str(last_error)[:500])}</code>"

    return (
        "💫 <b>Youseif</b> 💫\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>{safe_title}</b>\n"
        f"🆔 Stream <code>#{stream_id}</code>\n"
        f"{state_label(state)}\n"
        f"⏱ مدة التشغيل: <code>{html.escape(str(uptime))}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{media_line}\n"
        f"📡 المصدر: <code>{html.escape(str(source_type))}</code>\n"
        f"🎥 الدقة: <code>{html.escape(str(resolution))}</code> · FPS: <code>{html.escape(str(fps))}</code>\n"
        f"🔊 الصوت: <code>{html.escape(_codec_info(meta) if has_audio is not False else 'غير موجود')}</code>\n"
        f"📊 Bitrate: <code>{html.escape(real_br)}</code>\n"
        f"⚡ Speed: <code>{html.escape(speed)}</code>\n"
        f"🧮 Frames: <code>{html.escape(frames_text)}</code>\n"
        f"🔊 مستوى الصوت: <code>{html.escape(str(min(200, max(0, int(round(float(volume or 1.0) * 100))))))}%</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📡 حالة الاتصال:\n"
        f"{st(ffmpeg_ok, 'FFmpeg')} · {st(rtmp_ok and data_flow, 'Output / RTMP')} · {st(source_ok and data_flow, 'المصدر')}\n"
        f"🆔 PID: <code>{html.escape(str(pid))}</code>\n"
        f"🔄 محاولات الاستعادة: <code>{html.escape(str(reconnects))}</code>\n"
        f"{'🟠 التدفق متوقف مؤقتًا — تتم المعالجة' if stalled else '🟢 تدفق البيانات مؤكد' if data_flow else '🟡 في انتظار تدفق البيانات'}"
        f"{err_line}\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
