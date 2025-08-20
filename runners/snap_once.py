import time, json
from datetime import datetime
import pytz

from clients import stockbit
from logic.rolling import parse_market_mover, rupiah
from notif.telegram import send as tg_send

TZ = pytz.timezone("Asia/Jakarta")

def now_id():
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")

def _coerce_dict(x):
    """Kembalikan dict dari x; jika string JSON coba json.loads; selain itu -> None."""
    if isinstance(x, dict):
        return x
    if isinstance(x, str):
        try:
            j = json.loads(x)
            return j if isinstance(j, dict) else None
        except Exception:
            return None
    return None

def _extract_rt_list(rt_raw):
    """
    Ambil list item running-trade dari berbagai kemungkinan bentuk respons.
    """
    if isinstance(rt_raw, list):
        return rt_raw
    if isinstance(rt_raw, dict):
        # beberapa varian field yang mungkin
        for key in ("data", "result", "items"):
            v = rt_raw.get(key)
            if isinstance(v, list):
                return v
            if isinstance(v, dict) and "items" in v and isinstance(v["items"], list):
                return v["items"]
        # jika bentuknya dict tapi tidak ada list, anggap tidak ada data
        return []
    # bentuk lain (string, dll) -> tidak valid
    return []

def run(top_n=10, include_powerbuy=True, pb_limit=10, rt_limit=50, pb_interval="10m"):
    gainers = parse_market_mover(stockbit.top_gainer())[:top_n]
    values  = parse_market_mover(stockbit.top_value())[:top_n]

    rt_raw = stockbit.running_trade(limit=rt_limit)
    rt_list = _extract_rt_list(rt_raw)

    # ringkas RT value/lot per simbol (robust untuk item string/dict)
    agg = {}
    skipped = 0
    for raw in rt_list:
        t = _coerce_dict(raw)
        if not t:
            skipped += 1
            continue

        s = t.get("symbol") or t.get("stock") or t.get("code")
        if not s:
            skipped += 1
            continue

        try:
            price = int(t.get("price") or t.get("trade_price") or t.get("last") or 0)
        except Exception:
            price = 0
        try:
            lot = int(t.get("volume") or t.get("lot") or 0)
        except Exception:
            lot = 0
        try:
            val = int(t.get("value") or (price * lot * 100))
        except Exception:
            val = price * lot * 100

        cur = agg.get(s, {"value":0,"lot":0,"price":price})
        cur["value"] += max(0, val)
        cur["lot"]   += max(0, lot)
        if price:      # update last price jika ada
            cur["price"] = price
        agg[s] = cur

    lines = []
    lines.append(f"📊 Stockbit Snapshot {now_id()}")
    if skipped:
        lines.append(f"(info: {skipped} item RT di-skip karena format tidak dikenal)")

    lines.append("— Top Gainer —")
    for g in gainers:
        sym = g["symbol"]; chg = g["chg_pct"]; snap = agg.get(sym, {})
        lines.append(f"• {sym:<6} {str(chg)+'%':>6} | last≈{snap.get('price','-')} | RT val≈{rupiah(snap.get('value',0))}")

    lines.append("")
    lines.append("— Top Value —")
    for v in values:
        sym = v["symbol"]; val = v["value"]; snap = agg.get(sym, {})
        lines.append(f"• {sym:<6} {rupiah(val):>12} | last≈{snap.get('price','-')} | RT lot≈{snap.get('lot',0)}")

    if include_powerbuy:
        lines.append("")
        lines.append(f"— PowerBuy ({pb_interval}) —")
        # daftar simbol unik dari gainers + values
        uniq = []
        for x in gainers + values:
            s = x["symbol"]
            if s and s not in uniq:
                uniq.append(s)

        for sym in uniq[:pb_limit]:
            try:
                pb = stockbit.powerbuy(sym, interval=pb_interval)
                data = pb.get("data") if isinstance(pb, dict) else None
                intervals = []
                if isinstance(data, dict):
                    intervals = data.get("intervals") or data.get("items") or []
                if intervals:
                    last = intervals[-1]
                    bv = last.get("buy_value") or last.get("buyValue") or 0
                    sv = last.get("sell_value") or last.get("sellValue") or 0
                    total = (bv or 0) + (sv or 0)
                    br = (bv/total) if total else None
                    if br is not None:
                        lines.append(f"• {sym:<6} buy_ratio≈{br:.2f} | buy≈{rupiah(bv)} sell≈{rupiah(sv)}")
                    else:
                        lines.append(f"• {sym:<6} (PB data terbatas)")
                else:
                    lines.append(f"• {sym:<6} (no intervals)")
                time.sleep(0.25)
            except Exception as e:
                lines.append(f"• {sym:<6} (PB error: {e})")

    tg_send("\n".join(lines))

if __name__ == "__main__":
    run()
