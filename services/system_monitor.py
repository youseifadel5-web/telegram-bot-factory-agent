"""Live system stats for the resource dashboard — CPU, RAM, Disk, Network, Uptime.

Uses psutil when available (recommended, in requirements.txt) and transparently
falls back to /proc parsing if psutil can't be installed on a given host, so
the dashboard never just breaks.
"""
import time
import shutil
from pathlib import Path

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    psutil = None
    _HAS_PSUTIL = False

_START = time.time()
_prev_net = None
_prev_net_ts = None


# --------------------------------------------------------------------------- #
# /proc fallback (used only if psutil isn't installed)
# --------------------------------------------------------------------------- #
def _read_proc_stat():
    try:
        with open("/proc/stat") as f:
            line = f.readline()
        parts = line.split()
        nums = list(map(int, parts[1:8]))
        idle = nums[3] + (nums[4] if len(nums) > 4 else 0)
        total = sum(nums)
        return idle, total
    except Exception:
        return None, None


_prev_idle = None
_prev_total = None


def _cpu_percent_proc() -> float:
    global _prev_idle, _prev_total
    idle, total = _read_proc_stat()
    if idle is None:
        return 0.0
    if _prev_total is None:
        _prev_idle, _prev_total = idle, total
        time.sleep(0.05)
        idle2, total2 = _read_proc_stat()
        if idle2 is None:
            return 0.0
        idle, total = idle2, total2
    d_idle = idle - _prev_idle
    d_total = total - _prev_total
    _prev_idle, _prev_total = idle, total
    if d_total <= 0:
        return 0.0
    return max(0.0, min(100.0, (1 - d_idle / d_total) * 100))


def _ram_info_proc():
    try:
        mem = {}
        with open("/proc/meminfo") as f:
            for line in f:
                if ":" in line:
                    k, v = line.split(":")
                    mem[k.strip()] = int(v.strip().split()[0])
        total = mem.get("MemTotal", 1) * 1024
        avail = mem.get("MemAvailable", mem.get("MemFree", 0)) * 1024
        used = total - avail
        return used, total
    except Exception:
        return 0, 1


# --------------------------------------------------------------------------- #
# Public metrics — psutil-backed when available
# --------------------------------------------------------------------------- #
def cpu_percent() -> float:
    if _HAS_PSUTIL:
        return psutil.cpu_percent(interval=0.2)
    return _cpu_percent_proc()


def ram_info():
    if _HAS_PSUTIL:
        m = psutil.virtual_memory()
        return m.used, m.total
    return _ram_info_proc()


def disk_info(path: str = None):
    path = path or str(Path(__file__).resolve().parent.parent)
    try:
        u = shutil.disk_usage(path)
        return u.used, u.total
    except Exception:
        return 0, 1


def network_info():
    """Returns (bytes_sent_total, bytes_recv_total, send_rate_bps, recv_rate_bps)."""
    global _prev_net, _prev_net_ts
    now = time.time()
    if _HAS_PSUTIL:
        try:
            counters = psutil.net_io_counters()
            sent, recv = counters.bytes_sent, counters.bytes_recv
        except Exception:
            sent, recv = 0, 0
    else:
        try:
            sent = recv = 0
            with open("/proc/net/dev") as f:
                for line in f.readlines()[2:]:
                    parts = line.split()
                    iface = parts[0].strip(":")
                    if iface == "lo":
                        continue
                    recv += int(parts[1])
                    sent += int(parts[9])
        except Exception:
            sent, recv = 0, 0

    send_rate = recv_rate = 0.0
    if _prev_net is not None and _prev_net_ts is not None:
        dt = max(now - _prev_net_ts, 0.01)
        send_rate = max(0.0, (sent - _prev_net[0]) / dt)
        recv_rate = max(0.0, (recv - _prev_net[1]) / dt)
    _prev_net = (sent, recv)
    _prev_net_ts = now
    return sent, recv, send_rate, recv_rate


def process_count() -> int:
    if _HAS_PSUTIL:
        try:
            return len(psutil.pids())
        except Exception:
            return 0
    return 0


def ffmpeg_process_count() -> int:
    """How many ffmpeg processes are currently running on the box — useful to
    confirm "only one broadcast" is actually being enforced."""
    if not _HAS_PSUTIL:
        return -1
    n = 0
    try:
        for p in psutil.process_iter(["name", "cmdline"]):
            try:
                name = (p.info.get("name") or "").lower()
                cmdline = " ".join(p.info.get("cmdline") or []).lower()
                if "ffmpeg" in name or "ffmpeg" in cmdline:
                    n += 1
            except Exception:
                continue
    except Exception:
        return -1
    return n


def bar(pct: float, width: int = 7, fill: str = "🟩", empty: str = "⬜") -> str:
    pct = max(0, min(100, pct))
    n = int(round(width * pct / 100))
    return fill * n + empty * (width - n)


def format_bytes(n: float) -> str:
    n = float(n)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} PB"


def format_rate(bps: float) -> str:
    return f"{format_bytes(bps)}/s"


def uptime_str() -> str:
    s = int(time.time() - _START)
    h, r = divmod(s, 3600)
    m, sec = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def build_dashboard(tick: int = 0) -> str:
    cpu = cpu_percent()
    ru, rt = ram_info()
    du, dt = disk_info()
    _, _, send_rate, recv_rate = network_info()
    rp = (ru / rt * 100) if rt else 0
    dp = (du / dt * 100) if dt else 0
    ff_count = ffmpeg_process_count()
    engine = "psutil" if _HAS_PSUTIL else "/proc (fallback)"

    # FFmpeg availability + stream count
    try:
        from services.stream import stream_manager
        has_ff = stream_manager.has_ffmpeg()
        active = sum(1 for sid in stream_manager.processes if stream_manager.is_running(sid))
        ff_status = "🟢 يعمل" if has_ff else "🔴 غير متوفر"
        rtmp_status = "🟢 متصل" if active > 0 else "⚪ لا يوجد بث"
    except Exception:
        has_ff = False
        active = 0
        ff_status = "⚪ غير معروف"
        rtmp_status = "⚪ غير معروف"

    return (
        f"🖥 <b>حالة النظام</b> · Youseif\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚙️ <b>المعالج CPU</b>\n"
        f"{bar(cpu, 7, '🟩')} <b>{cpu:.0f}%</b>\n\n"
        f"🧠 <b>الرام RAM</b>\n"
        f"{bar(rp, 7, '🟦')} <b>{rp:.0f}%</b>\n"
        f"<code>{format_bytes(ru)} / {format_bytes(rt)}</code>\n\n"
        f"💾 <b>التخزين</b>\n"
        f"{bar(dp, 7, '🟪')} <b>{dp:.0f}%</b>\n"
        f"<code>{format_bytes(du)} / {format_bytes(dt)}</code>\n\n"
        f"🌐 <b>الشبكة</b>\n"
        f"⬆️ {format_rate(send_rate)}   ⬇️ {format_rate(recv_rate)}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎞 FFmpeg: {ff_status}\n"
        f"📡 RTMP: {rtmp_status}\n"
        f"📺 عدد البثوث الحالية: <b>{active}</b>\n"
        f"🎞 عمليات FFmpeg: <b>{ff_count}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⏱ تشغيل البوت: <code>{uptime_str()}</code>\n"
        f"🟢 حالة البوت: <b>Online</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Live Monitor ({engine}) · tick {tick}</i>"
    )
