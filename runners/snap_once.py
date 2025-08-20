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
    # Support struktur baru: {"data":{"running_trade":[...]}}
    if isinstance(rt_raw, dict):
        d = rt_raw.get("data")
        if isinstance(d, dict) and isinstance(d.get("running_trade"), list):
            return d["running_trade"]
        # fallback lama
        for key in ("data", "result", "items"):
            v = rt_raw.get(key)
            if isinstance(v, list):
                return v
            if isinstance(v, dict) and isinstance(v.get("items"), list):
                return v["items"]
        return []
    if isinstance(rt_raw, list):
        return rt_raw
    return []


def run(top_n=10, include_powerbuy=True, pb_limit=10, rt_limit=500, pb_interval="10m"):
    gainers_raw = stockbit.top_gainer()
    values_raw  = stockbit.top_value()

    gainers = parse_market_mover(gainers_raw)[:top_n]
    values  = parse_market_mover(values_raw)[:top_n]

    rt_raw  = stockbit.running_trade(limit=rt_limit)
    rt_list = _extract_rt_list(rt_raw)

    # ringkas RT
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
        if price:
            cur["price"] = price
        agg[s] = cur

    lines = []
    lines.append(f"📊 Stockbit Snapshot {now_id()}")
    # ringkas jumlah untuk bantu debug
    lines.append(f"(info: gainers={len(gainers)}, values={len(values)}, rt_items={len(rt_list)}, rt_skipped={skipped})")

    lines.append("— Top Gainer —")
    if not gainers:
        lines.append("• (kosong) — struktur API mungkin berubah; parser akan menyesuaikan.")
    for g in gainers:
        sym = g["symbol"]; chg = g["chg_pct"]; snap = agg.get(sym, {})
        lines.append(f"• {sym:<6} {str(chg)+'%':>6} | last≈{snap.get('price','-')} | RT val≈{rupiah(snap.get('value',0))}")

    lines.append("")
    lines.append("— Top Value —")
    if not values:
        lines.append("• (kosong)")
    for v in values:
        sym = v["symbol"]; val = v["value"]; snap = agg.get(sym, {})
        lines.append(f"• {sym:<6} {rupiah(val):>12} | last≈{snap.get('price','-')} | RT lot≈{snap.get('lot',0)}")

    if include_powerbuy:
        lines.append("")
        lines.append(f"— PowerBuy ({pb_interval}) —")
        uniq = []
        for x in gainers + values:
            s = x["symbol"]
            if s and s not in uniq:
                uniq.append(s)
        if not uniq:
            lines.append("• (skip: tidak ada simbol dari gainers/values)")
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
