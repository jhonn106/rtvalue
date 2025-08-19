import time
from datetime import datetime
import pytz

from clients import stockbit
from logic.rolling import parse_market_mover, rupiah
from notif.telegram import send as tg_send

TZ = pytz.timezone("Asia/Jakarta")

def now_id():
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")

def run(top_n=10, include_powerbuy=True, pb_limit=10, rt_limit=50, pb_interval="10m"):
    gainers = parse_market_mover(stockbit.top_gainer())[:top_n]
    values = parse_market_mover(stockbit.top_value())[:top_n]
    rt_raw = stockbit.running_trade(limit=rt_limit)
    rt_list = rt_raw.get("data", []) if isinstance(rt_raw, dict) else []

    agg = {}
    for t in rt_list:
        s = t.get("symbol") or t.get("stock") or t.get("code")
        if not s: continue
        price = int(t.get("price") or 0)
        lot = int(t.get("volume") or t.get("lot") or 0)
        val = int(t.get("value") or price * lot * 100)
        cur = agg.get(s, {"value":0,"lot":0,"price":price})
        cur["value"] += val
        cur["lot"] += lot
        cur["price"] = price or cur["price"]
        agg[s] = cur

    lines = []
    lines.append(f"📊 Stockbit Snapshot {now_id()}")
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
        unique_syms = []
        for x in gainers + values:
            s = x["symbol"]
            if s and s not in unique_syms:
                unique_syms.append(s)
        for sym in unique_syms[:pb_limit]:
            try:
                pb = stockbit.powerbuy(sym, interval=pb_interval)
                data = pb.get("data") or {}
                intervals = data.get("intervals") or []
                if intervals:
                    last = intervals[-1]
                    bv = last.get("buy_value") or last.get("buyValue") or 0
                    sv = last.get("sell_value") or last.get("sellValue") or 0
                    br = (bv/(bv+sv)) if (bv+sv)>0 else None
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
