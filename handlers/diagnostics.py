"""Admin diagnostics: /diagnose /probe /oscar_test"""
from __future__ import annotations

import html
import logging
from telegram import Update
from telegram.ext import ContextTypes

from config import ADMIN_ID
from utils.helpers import is_admin

logger = logging.getLogger(__name__)


def _admin(uid: int) -> bool:
    return is_admin(uid, ADMIN_ID)


async def diagnose_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not _admin(update.effective_user.id):
        return
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "🔍 <b>Diagnose</b>\n\nUsage:\n<code>/diagnose https://example.com/stream</code>",
            parse_mode="HTML",
        )
        return
    url = " ".join(args).strip().strip("<>")
    status = await update.message.reply_text("🔍 جاري فحص المصدر...")
    try:
        from services.media.source_probe_v2 import probe_media_url
        result = await probe_media_url(url)
    except Exception as e:
        logger.exception("diagnose: %s", e)
        await status.edit_text(f"❌ فشل التشخيص: {e}")
        return

    hls = result.get("hls") or {}
    ff = result.get("ffprobe") or {}
    var = result.get("variant") or {}
    lines = [
        "🛠 <b>تشخيص المصدر</b>",
        "━━━━━━━━━━━━",
        f"🌐 <b>URL:</b>\n<code>{html.escape((result.get('url') or '')[:160])}</code>",
        f"➡️ <b>Final:</b>\n<code>{html.escape((result.get('final_url') or '')[:160])}</code>",
        "",
        f"📡 <b>Type:</b> {html.escape(str(result.get('type') or '—'))}",
        f"📄 <b>Content-Type:</b> {html.escape(str(result.get('content_type') or '—'))}",
        "",
        f"🎞 <b>HLS:</b> {'نعم' if hls.get('is_hls') else 'لا'}"
        f" · Master={'نعم' if hls.get('is_master') else 'لا'}"
        f" · Variants={hls.get('variants', 0)}"
        f" · Segments={hls.get('segment_count', 0)}",
    ]
    if var:
        lines.append(
            f"🎯 <b>Variant:</b> {html.escape(str(var.get('resolution') or '—'))}"
            f" · bw={var.get('bandwidth') or '—'}"
        )
    if hls.get("first_segment"):
        lines.append(f"📦 <b>First segment:</b>\n<code>{html.escape(str(hls['first_segment'])[:120])}</code>")
    lines += [
        "",
        f"🧪 <b>FFprobe:</b> {'✅' if ff.get('ok') else '❌'}",
        f"🎬 Video: {ff.get('has_video')} · 🎵 Audio: {ff.get('has_audio')}",
        f"🎛 Codec: {html.escape(str(ff.get('codec') or '—'))} · {html.escape(str(ff.get('format') or '—'))}",
        f"📶 Quality: {html.escape(str(ff.get('quality') or '—'))}",
    ]
    if result.get("error"):
        lines.append(f"\n❌ <b>Error ({html.escape(str(result.get('stage')))}):</b> {html.escape(str(result['error'])[:200])}")
    if ff.get("solution"):
        lines.append(f"💡 {html.escape(str(ff['solution'])[:200])}")
    lines.append(f"\n{'✅ PASS' if result.get('ok') else '❌ FAIL'}")
    try:
        await status.edit_text("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)
    except Exception:
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def oscar_test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not _admin(update.effective_user.id):
        return
    msg = await update.message.reply_text("🧪 اختبار Oscar API...")
    results = []
    try:
        from services.oscar import movies, series, channels, taxonomy
        try:
            m = await movies.movies(page=1, limit=3)
            results.append(f"✅ movies: {len(m)} items")
        except Exception as e:
            results.append(f"❌ movies: {e}")
        try:
            s = await series.series(page=1, limit=3)
            results.append(f"✅ series: {len(s)} items")
        except Exception as e:
            results.append(f"❌ series: {e}")
        try:
            c = await channels.channel_show(1)
            results.append(f"✅ channel_show(1): {'ok' if c else 'empty'}")
        except Exception as e:
            results.append(f"❌ channels: {e}")
        try:
            g = await taxonomy.genres()
            results.append(f"✅ genres: {type(g).__name__}")
        except Exception as e:
            results.append(f"❌ genres: {e}")
    except Exception as e:
        results.append(f"❌ import/client: {e}")
    await msg.edit_text("🧪 <b>Oscar API Test</b>\n\n" + "\n".join(results), parse_mode="HTML")


async def probe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Alias for diagnose."""
    return await diagnose_command(update, context)


async def hls_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /hls <url> — HLS-only analysis."""
    if not update.effective_user or not _admin(update.effective_user.id):
        return
    args = context.args or []
    if not args:
        await update.message.reply_text("Usage: <code>/hls URL</code>", parse_mode="HTML")
        return
    url = " ".join(args).strip().strip("<>")
    msg = await update.message.reply_text("🎞 تحليل HLS...")
    try:
        from services.media.hls_detector import detect_hls, pick_variant
        info = await detect_hls(url)
        lines = [
            "🎞 <b>HLS Analysis</b>",
            f"HLS: {'✅' if info.is_hls else '❌'}",
            f"Master: {'نعم' if info.is_master else 'لا'} · Media: {'نعم' if info.is_media else 'لا'}",
            f"Content-Type: <code>{html.escape(info.content_type or '—')}</code>",
            f"Final: <code>{html.escape((info.final_url or '')[:140])}</code>",
            f"Variants: {len(info.variants)} · Segments: {info.segment_count}",
        ]
        if info.variants:
            best = pick_variant(info, "best")
            lines.append(f"Best: {html.escape(best.resolution or '—')} · bw={best.bandwidth}")
            for v in info.variants[:6]:
                lines.append(f"• {html.escape(v.resolution or '?')} · {v.bandwidth}")
        if info.first_segment:
            lines.append(f"First segment:\n<code>{html.escape(info.first_segment[:120])}</code>")
        if info.error:
            lines.append(f"❌ {html.escape(info.error[:200])}")
        await msg.edit_text("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        await msg.edit_text(f"❌ {e}")


async def streams_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not _admin(update.effective_user.id):
        return
    try:
        from database import db
        from services.stream import stream_manager
        streams = await db.get_active_streams() or []
        if not streams:
            await update.message.reply_text("📡 لا توجد بثوث نشطة.")
            return
        lines = ["📡 <b>Active streams</b>\n"]
        for s in streams[:20]:
            sid = s.get("id")
            running = stream_manager.is_running(sid)
            lines.append(
                f"{'🟢' if running else '🔴'} #{sid} {html.escape(str(s.get('title') or '')[:40])} · user={s.get('user_id')}"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")
