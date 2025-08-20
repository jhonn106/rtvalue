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
    if isinstance(rt_raw, list):
        return rt_raw
    if isinstance(rt_raw, dict):
        for key in ("data", "result", "items"):
            v = rt_raw.get(key)
            if isinstance(v, list):
                return v
            if isinstance(v, dict) and isinstance(v.get("items"), list):
                return v["items"]
        return []
    return []

def _pretty(obj):
    try:
        return json.dumps(obj, ensure_ascii=False)[:800]
    except Exception:
        return str(obj)[:800]

def run(top_n=10, include_powerbuy=True, pb_limit=10, rt_limit=50, pb_interval="10m"):
    # --- TOP GAINER / VALUE (utama)
    gainers_raw = stockbit.top_gainer()
    values_raw  = stockbit.top_value()

    gainers = parse_market_mover(gainers_raw)[:top_n]
    values  = parse_market_mover(values_raw)[:top_n]

    # Fallback: coba endpoint tanpa filter jika kosong
    used_fallback_mm = False
    if not gainers or not values:
        try:
            g2 = stockbit.top_gainer_simple()
            v2 = stockbit.top_value_simple()
            pg2 = parse_market_mover(g2)[:top_n]
            pv2 = parse_market_mover(v2)[:top_n]
            if not gainers: gainers = pg2
            if not values:  values  = pv2
            used_fallback_mm = True
        except Exception as e:
            # biarkan kosong, nanti kita print RAW
            pass

    # --- RUNNING TRADE (utama)
    rt_raw  = stockbit.running_trade(limit=rt_limit)
    rt_list = _extract_rt_list(rt_raw)
    used_fallback_rt = False
    if not rt_list:
        try:
            rt2 = stockbit.running_trade_simple()
            rt_list = _extract_rt_list(rt2)
            used_fallback_rt = True
        except Exception:
            pass

    # --- Ringkas RT
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
        try:  price = int(t.get("price") or t.get("trade_price") or t.get("last") or 0)
        except: price = 0
        try:  lot   = int(t.get("volume") or t.get("lot") or 0)
        except: lot = 0
        try:  val   = int(t.get("value") or (price * lot * 100))
        except: val = price * lot * 100

        cur = agg.get(s, {"value":0,"lot":0,"price":price})
        cur["value"] += max(0, val)
        cur["lot"]   += max(0, lot)
        if price:
            cur["price"] = price
        agg[s] = cur

    # --- Compose laporan
    lines = []
    lines.append(f"📊 Stockbit Snapshot {now_id()}")
    lines.append(f"(info: gainers={len(gainers)}, values={len(values)}, rt_items={len(rt_list)}, rt_skipped={skipped}, mm_fallback={used_fallback_mm}, rt_fallback={used_fallback_rt})")

    # Jika masih kosong, tampilkan RAW untuk diagnosa cepat
    if not gainers:
        lines.append("RAW gainers (cuplikan): " + _pretty(gainers_raw))
    if not values:
        lines.append("RAW values (cuplikan): " + _pretty(values_raw))
    if not rt_list:
        lines.append("RAW running-trade (cuplikan): " + _pretty(rt_raw))

    lines.append("— Top Gainer —")
    if not gainers:
        lines.append("• (kosong)")
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
