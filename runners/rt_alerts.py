import os, time, json, requests
from datetime import datetime, timedelta
import pytz
from clients import stockbit

TZ = pytz.timezone("Asia/Jakarta")

# Sesi
MORNING_START = (9, 0)
MORNING_END   = (12, 0)
AFTER_START   = (13, 30)
AFTER_END     = (16, 15)

THRESHOLD_IDR = 10_000_000
POLL_SECONDS  = 15
DEDUP_MINUTES = 15

TG_TOKEN   = os.environ.get("TG_TOKEN")
TG_CHAT_ID2 = os.environ.get("TG_CHAT_ID2") or os.environ.get("TG_CHAT_ID_2")

def _now(): return datetime.now(TZ)
def _dt(h, m):
    n = _now()
    return TZ.localize(datetime(n.year, n.month, n.day, h, m, 0))

def current_session():
    n = _now()
    s1, e1 = _dt(*MORNING_START), _dt(*MORNING_END)
    s2, e2 = _dt(*AFTER_START), _dt(*AFTER_END)
    if s1 <= n < e1: return s1, e1
    if s2 <= n < e2: return s2, e2
    return None

def _extract_rt_list(rt_raw):
    if isinstance(rt_raw, dict):
        d = rt_raw.get("data")
        if isinstance(d, dict) and isinstance(d.get("running_trade"), list):
            return d["running_trade"]
    if isinstance(rt_raw, list):
        return rt_raw
    return []

def _to_int(x):
    try: return int(float(str(x).replace(",", "").strip()))
    except Exception: return 0

def _rupiah(n):
    try: return f"Rp{int(n):,}".replace(",", ".")
    except Exception: return str(n)

def _pb_buy_ratio_latest(symbol, interval="10m"):
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
        if not rows: return None
        last = rows[-1]
        b = _to_int((last.get("buy") or {}).get("lot"))
        s = _to_int((last.get("sell") or {}).get("lot"))
        tot = b + s
        return (b / tot) if tot > 0 else None
    except Exception:
        return None

def _send(text: str):
    if not TG_TOKEN or not TG_CHAT_ID2:
        print("[RT ALERT]", text); return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT_ID2, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
        if r.status_code != 200:
            print("[RT WARN]", r.text)
    except Exception as e:
        print("[RT ERR]", e)

def main():
    sess = current_session()
    if not sess:
        print("[RT ALERT] start di luar sesi, exit.")
        return
    start, end = sess
    print(f"[RT ALERT] running session: {start} → {end}")

    seen = {}
    while True:
        now = _now()
        if now >= end:
            print("[RT ALERT] session ended, exit.")
            break

        try:
            rt = stockbit.running_trade(limit=200)
            items = _extract_rt_list(rt)
            for t in items:
                if not isinstance(t, dict) or t.get("action") != "buy":
                    continue
                code  = t.get("code") or t.get("symbol") or t.get("stock")
                price = _to_int(t.get("price") or t.get("trade_price") or 0)
                lot   = _to_int(t.get("lot") or t.get("volume") or 0)
                tid   = t.get("trade_number") or t.get("id")
                if not code or price <= 0 or lot <= 0 or not tid:
                    continue
                val = price * lot * 100
                if val < THRESHOLD_IDR:
                    continue
                if tid in seen and (now - seen[tid]) < timedelta(minutes=DEDUP_MINUTES):
                    continue
                seen[tid] = now
                gain = t.get("change") or t.get("chg") or "-"
                tm   = t.get("time") or now.strftime("%H:%M")
                br = _pb_buy_ratio_latest(code, "10m")
                pbuy = "-" if br is None else f"{br*100:.0f}%"
                msg = f"[{tm}] {code} {price} {gain} {_rupiah(val)}  PBuy:{pbuy}"
                _send(msg)
            # bersihkan cache
            cutoff = now - timedelta(minutes=DEDUP_MINUTES)
            for k in list(seen.keys()):
                if seen[k] < cutoff:
                    del seen[k]
        except Exception as e:
            print("[RT ALERT ERROR]", e)

        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()
