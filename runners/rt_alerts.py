# runners/rt_alerts.py
import os, time, json, requests
from datetime import datetime, timedelta
import pytz

from clients import stockbit

# =================== Konfigurasi ===================
TZ = pytz.timezone("Asia/Jakarta")

JAK_START = (9, 0)     # 09:00 WIB
JAK_END   = (16, 15)   # 16:15 WIB  (ubah ke (16, 0) jika mau stop 16:00)

THRESHOLD_IDR   = 10_000_000   # nilai minimal transaksi buy (Rp)
POLL_SECONDS    = 15           # interval polling RT (detik)
DEDUP_MINUTES   = 15           # simpan id trade utk anti-duplikat (menit)

TG_TOKEN   = os.environ.get("TG_TOKEN")
TG_CHAT_ID2 = os.environ.get("TG_CHAT_ID2") or os.environ.get("TG_CHAT_ID_2")

# =================== Utils ===================
def _now():
    return datetime.now(TZ)

def _market_open_today():
    n = _now()
    return TZ.localize(datetime(n.year, n.month, n.day, JAK_START[0], JAK_START[1], 0))

def _market_close_today():
    n = _now()
    return TZ.localize(datetime(n.year, n.month, n.day, JAK_END[0], JAK_END[1], 0))

def _in_trading_window():
    n = _now()
    return (n.weekday() < 5) and (_market_open_today() <= n < _market_close_today())

def _extract_rt_list(rt_raw):
    if isinstance(rt_raw, dict):
        d = rt_raw.get("data")
        if isinstance(d, dict) and isinstance(d.get("running_trade"), list):
            return d["running_trade"]
    if isinstance(rt_raw, list):
        return rt_raw
    return []

def _to_int(x):
    try:
        return int(float(str(x).replace(",", "").strip()))
    except Exception:
        return 0

def _rupiah(n):
    try:
        return f"Rp{int(n):,}".replace(",", ".")
    except Exception:
        return str(n)

def _pb_buy_ratio_latest(symbol, interval="10m"):
    """Ambil rasio buy pada bucket terbaru PowerBuy (10m)."""
    try:
        pb = stockbit.powerbuy(symbol, interval=interval)
        d = pb.get("data") if isinstance(pb, dict) else None
        rows = []
        if isinstance(d, dict) and isinstance(d.get("book"), list):
            rows = d["book"]
        elif isinstance(d, dict) and isinstance(d.get("intervals"), list):
            rows = d["intervals"]
        elif isinstance(d, dict) and isinstance(d.get("items"), list):
            rows = d["items"]
        if not rows:
            return None
        last = rows[-1]
        buy = last.get("buy") or {}
        sell = last.get("sell") or {}
        b = _to_int(buy.get("lot"))
        s = _to_int(sell.get("lot"))
        tot = b + s
        return (b / tot) if tot > 0 else None
    except Exception:
        return None

def _send_to_chat2(text: str):
    """Kirim ke Telegram #2; jika token/chat kosong → print ke log."""
    if not TG_TOKEN or not TG_CHAT_ID2:
        print("[RT ALERT]", text)
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT_ID2, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
        if r.status_code != 200:
            print("[RT ALERT WARN]", r.text)
    except Exception as e:
        print("[RT ALERT ERR]", e)

# =================== Main loop ===================
def main():
    start_ts = _now()
    seen = {}  # trade_number -> datetime (untuk anti-dup)

    print("[RT ALERT] Started. Window:", _market_open_today(), "→", _market_close_today())

    while True:
        now = _now()

        # === STOP otomatis saat lewat jam tutup ===
        if now >= _market_close_today():
            print("[RT ALERT] Market closed — exiting loop.")
            break

        # Di luar hari kerja → stop juga
        if now.weekday() >= 5:
            print("[RT ALERT] Weekend — exiting loop.")
            break

        # Jika sebelum jam buka, tidur pendek sampai buka
        if now < _market_open_today():
            time.sleep(min(60, (_market_open_today() - now).total_seconds()))
            continue

        try:
            rt = stockbit.running_trade(limit=200)
            items = _extract_rt_list(rt)

            # Proses hanya 'buy' dan di atas threshold
            for t in items:
                if not isinstance(t, dict):
                    continue
                if t.get("action") != "buy":
                    continue

                code  = t.get("code") or t.get("symbol") or t.get("stock")
                price = _to_int(t.get("price") or t.get("trade_price") or 0)
                lot   = _to_int(t.get("lot") or t.get("volume") or 0)
                tid   = t.get("trade_number") or t.get("id")

                if not code or price <= 0 or lot <= 0 or not tid:
                    continue

                val = price * lot * 100  # 1 lot = 100 saham
                if val < THRESHOLD_IDR:
                    continue

                # Anti-duplikat dalam jendela pendek
                nowts = now
                if tid in seen and (nowts - seen[tid]) < timedelta(minutes=DEDUP_MINUTES):
                    continue
                seen[tid] = nowts

                gain = t.get("change") or t.get("chg") or "-"
                tm   = t.get("time") or nowts.strftime("%H:%M")

                br = _pb_buy_ratio_latest(code, "10m")
                pbuy = "-" if br is None else f"{br*100:.0f}%"

                msg = f"[{tm}] {code} {price} {gain} {_rupiah(val)}  PBuy:{pbuy}"
                _send_to_chat2(msg)

            # Bersihkan cache anti-dup yang kadaluarsa
            cutoff = now - timedelta(minutes=DEDUP_MINUTES)
            for k in list(seen.keys()):
                if seen[k] < cutoff:
                    del seen[k]

        except Exception as e:
            print("[RT ALERT ERROR]", e)

        time.sleep(POLL_SECONDS)

    print("[RT ALERT] Done.")

if __name__ == "__main__":
    main()
