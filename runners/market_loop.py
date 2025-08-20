import os, time, datetime, pytz

from runners.snap_once import run as run_snapshot
from notif.telegram import send as tg_send  # tetap untuk fallback log

TZ = pytz.timezone("Asia/Jakarta")

def now_id():
    return datetime.datetime.now(TZ)

def send_snapshot():
    # kamu bisa ubah parameter default di snap_once.run kalau perlu
    run_snapshot()

def sleep_until(target_dt):
    """Tidur sampai target (Asia/Jakarta)."""
    while True:
        now = now_id()
        delta = (target_dt - now).total_seconds()
        if delta <= 0:
            return
        time.sleep(min(delta, 15))

def next_run_after(now):
    """
    Balikkan datetime run berikutnya sesuai aturan:
      - sebelum 09:00 → 09:00 (setelah trigger 08:55)
      - 09:00–10:00 → tiap 2 menit
      - 10:00–16:15 → tiap 10 menit
      - di luar jam itu → stop (return None)
    """
    h, m = now.hour, now.minute
    today = now.date()

    # batas pasar: 16:15
    end = TZ.localize(datetime.datetime(now.year, now.month, now.day, 16, 15, 0))

    if now < TZ.localize(datetime.datetime(now.year, now.month, now.day, 9, 0)):
        return TZ.localize(datetime.datetime(now.year, now.month, now.day, 9, 0))

    if now >= TZ.localize(datetime.datetime(now.year, now.month, now.day, 9, 0)) and now < TZ.localize(datetime.datetime(now.year, now.month, now.day, 10, 0)):
        # tiap 2 menit
        minute = (now.minute // 2) * 2
        base = TZ.localize(datetime.datetime(now.year, now.month, now.day, now.hour, minute, 0))
        nxt = base + datetime.timedelta(minutes=2)
        return min(nxt, TZ.localize(datetime.datetime(now.year, now.month, now.day, 10, 0)))

    if now >= TZ.localize(datetime.datetime(now.year, now.month, now.day, 10, 0)) and now < end:
        # tiap 10 menit
        minute = (now.minute // 10) * 10
        base = TZ.localize(datetime.datetime(now.year, now.month, now.day, now.hour, minute, 0))
        nxt = base + datetime.timedelta(minutes=10)
        return min(nxt, end)

    return None  # selesai untuk hari ini

def main():
    # satu kali tembakan awal sekitar 08:55 (workflow akan start ±08:55 WIB)
    now = now_id()
    if now.hour < 9 or (now.hour == 9 and now.minute == 0 and now.second < 10):
        try:
            send_snapshot()
        except Exception as e:
            tg_send(f"[Snapshot awal] error: {e}")

    # loop sampai 16:15
    while True:
        now = now_id()
        # weekend: keluar
        if now.weekday() >= 5:
            break
        nxt = next_run_after(now)
        if not nxt:
            break
        sleep_until(nxt)
        try:
            send_snapshot()
        except Exception as e:
            tg_send(f"[Snapshot jadwal] error: {e}")
        time.sleep(1)

if __name__ == "__main__":
    main()
