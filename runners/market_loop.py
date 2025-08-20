import time, datetime, pytz
from notif.telegram import send as tg_send
from runners.snap_once import run as run_snapshot

TZ = pytz.timezone("Asia/Jakarta")

# Sesi pasar
MORNING_START = (9, 0)
MORNING_END   = (12, 0)
AFTER_START   = (13, 30)
AFTER_END     = (16, 15)

def now_id():
    return datetime.datetime.now(TZ)

def _dt(hour, minute):
    n = now_id()
    return TZ.localize(datetime.datetime(n.year, n.month, n.day, hour, minute, 0))

def current_session():
    """Return (start_dt, end_dt) untuk sesi yang sedang berjalan; else None."""
    n = now_id()
    s1, e1 = _dt(*MORNING_START), _dt(*MORNING_END)
    s2, e2 = _dt(*AFTER_START), _dt(*AFTER_END)
    if s1 <= n < e1:
        return s1, e1
    if s2 <= n < e2:
        return s2, e2
    return None

def next_tick(now):
    """Irama kirim: <10:00 tiap 2 menit, >=10:00 tiap 10 menit, batas sesi."""
    s, e = current_session()
    if not s:
        return None
    if now < _dt(10, 0):
        step = 2
        base_min = (now.minute // 2) * 2
        base = TZ.localize(datetime.datetime(now.year, now.month, now.day, now.hour, base_min, 0))
        nxt = base + datetime.timedelta(minutes=step)
    else:
        step = 10
        base_min = (now.minute // 10) * 10
        base = TZ.localize(datetime.datetime(now.year, now.month, now.day, now.hour, base_min, 0))
        nxt = base + datetime.timedelta(minutes=step)
    return min(nxt, e)

def sleep_until(dt):
    while True:
        d = (dt - now_id()).total_seconds()
        if d <= 0: return
        time.sleep(min(d, 15))

def main():
    # snapshot awal saat job dimulai (08:55/13:30) lalu lanjut sesuai irama
    try:
        run_snapshot()
    except Exception as e:
        tg_send(f"[market_loop] snapshot awal error: {e}")

    while True:
        sess = current_session()
        if not sess:
            # di luar sesi -> selesai (biarkan cron sesi berikutnya yang memulai lagi)
            break
        nxt = next_tick(now_id())
        if not nxt:
            break
        sleep_until(nxt)
        try:
            run_snapshot()
        except Exception as e:
            tg_send(f"[market_loop] snapshot error: {e}")
        time.sleep(1)

if __name__ == "__main__":
    main()
