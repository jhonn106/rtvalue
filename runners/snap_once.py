import time, json
from datetime import datetime
import pytz

from clients import stockbit
from logic.rolling import parse_market_mover, rupiah
from notif.telegram import send as tg_send

TZ = pytz.timezone("Asia/Jakarta")

# ============ Helpers format ============
def now_id():
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")

def id_int(n):
    """Integer → '1.234.567'."""
    try:
        return f"{int(float(n)):,}".replace(",", ".")
    except Exception:
        return str(n)

def id_float2(x):
    """Float → '12,34' → pakai koma desimal & titik ribuan (sesuai kebiasaan)."""
    try:
        s = f"{float(x):,.2f}"
        s = s.replace(",", "X").replace(".", ",").replace("X", ".")
        return s
    except Exception:
        return str(x)

def pct(x):
    try:
        return f"{float(x):.2f}%"
    except Exception:
        return str(x)

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
    """Support struktur baru: {'data': {'running_trade': [...]}} + fallback lama."""
    if isinstance(rt_raw, dict):
        d = rt_raw.get("data")
        if isinstance(d, dict) and isinstance(d.get("running_trade"), list):
            return d["running_trade"]
        for key in ("data", "result", "items"):
            v = rt_raw.get(key)
            if isinstance(v, list): return v
            if isinstance(v, dict) and isinstance(v.get("items"), list): return v["items"]
        return []
    if isinstance(rt_raw, list):
        return rt_raw
    return []

def _pretty(obj, n=800):
    try:
        return json.dumps(obj, ensure_ascii=False)[:n]
    except Exception:
        return str(obj)[:n]

def _to_num(s):
    if s is None: return 0
    if isinstance(s, (int, float)): return int(s)
    s = str(s).strip()
    if s in ("", "-", "—"): return 0
    s = s.replace(",", "").replace(".", "").replace("%", "")
    try:
        return int(float(s))
    except Exception:
        return 0

# ============ Main ============

def run(top_n=10, include_powerbuy=True, pb_limit=10, rt_limit=500, pb_interval="10m"):
    # --- TOP GAINER / VALUE
    gainers_raw = stockbit.top_gainer()
    values_raw  = stockbit.top_value()

    gainers = parse_market_mover(gainers_raw)[:top_n]
    values  = parse_market_mover(values_raw)[:top_n]

    # --- RUNNING TRADE
    rt_raw  = stockbit.running_trade(limit=rt_limit)
    rt_list = _extract_rt_list(rt_raw)

    # --- Aggregate RT per simbol
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
            price = int(float(t.get("price") or t.get("trade_price") or t.get("last") or 0))
        except Exception:
            price = 0
        try:
            lot = int(float(t.get("lot") or t.get("volume") or 0))
        except Exception:
            lot = 0
        try:
            val = int(float(t.get("value") or (price * lot * 100)))
        except Exception:
            val = price * lot * 100

        cur = agg.get(s, {"value":0,"lot":0,"price":price})
        cur["value"] += max(0, val)
        cur["lot"]   += max(0, lot)
        if price:
            cur["price"] = price
        agg[s] = cur

    # ====== Compose report (rapi) ======
    lines = []
    lines.append(f"📊 Stockbit Snapshot {now_id()}")
    lines.append(f"(info: gainers={len(gainers)}, values={len(values)}, rt_items={len(rt_list)}, rt_skipped={skipped})")
    lines.append("")

        # --- TABEL: Top Gainer (symbol · %kenaikan · last · value)
    lines.append("— Top Gainer —")
    if not gainers:
        lines.append("  (kosong)")
    else:
        lines.append("  Symbol  |   % Up   |  Last  |        Value")
        lines.append("  --------+----------+--------+----------------")
        for g in gainers:
            sym = g["symbol"]
            chg = pct(g["chg_pct"] if g["chg_pct"] is not None else 0)
            last = id_int(g.get("last") or 0) if (g.get("last") is not None) else "-"
            val = rupiah(g["value"] if g["value"] is not None else 0)
            lines.append(f"  {sym:<7} | {chg:>8} | {last:>6} | {val:>14}")
    lines.append("")

    # --- TABEL: Top Value (symbol · %kenaikan · last · value)
    lines.append("— Top Value —")
    if not values:
        lines.append("  (kosong)")
    else:
        lines.append("  Symbol  |   % Up   |  Last  |        Value")
        lines.append("  --------+----------+--------+----------------")
        for v in values:
            sym = v["symbol"]
            chg = pct(v["chg_pct"] if v["chg_pct"] is not None else 0)
            last = id_int(v.get("last") or 0) if (v.get("last") is not None) else "-"
            val = rupiah(v["value"] if v["value"] is not None else 0)
            lines.append(f"  {sym:<7} | {chg:>8} | {last:>6} | {val:>14}")
    lines.append("")


    # --- TABEL: RT Most Active (by value)
    lines.append("— RT Most Active (last window) —")
    if not agg:
        lines.append("  (tidak ada data RT)")
    else:
        lines.append("  Symbol  |  Last  |   Lot   |     Value")
        lines.append("  --------+--------+---------+----------------")
        top_rt = sorted(agg.items(), key=lambda kv: kv[1]["value"], reverse=True)[:10]
        for sym, m in top_rt:
            last = str(m.get("price", "-")) if m.get("price") else "-"
            lot  = id_int(m.get("lot", 0))
            val  = rupiah(m.get("value", 0))
            lines.append(f"  {sym:<7} | {last:>6} | {lot:>7} | {val:>14}")
    lines.append("")

    # --- TABEL: PowerBuy (trade-book)
    if include_powerbuy:
        lines.append(f"— PowerBuy ({pb_interval}) —")

        # daftar unik dari gainers + values
        uniq = []
        for x in gainers + values:
            s = x["symbol"]
            if s and s not in uniq:
                uniq.append(s)

        def _extract_pb_rows(pb_obj):
            if not isinstance(pb_obj, dict): return []
            d = pb_obj.get("data")
            if isinstance(d, dict) and isinstance(d.get("book"), list):
                return d["book"]
            # fallback lama
            if isinstance(d, dict) and isinstance(d.get("intervals"), list):
                return d["intervals"]
            if isinstance(d, dict) and isinstance(d.get("items"), list):
                return d["items"]
            return []

        # Kumpulkan ringkasan PB (ambil baris terakhir untuk setiap simbol)
        pb_rows = []
        for sym in uniq[:pb_limit]:
            try:
                pb = stockbit.powerbuy(sym, interval=pb_interval)
                rows = _extract_pb_rows(pb)
                if rows:
                    last = rows[-1]
                    buy = last.get("buy") or {}
                    sell = last.get("sell") or {}
                    buy_lot  = _to_num(buy.get("lot"))
                    sell_lot = _to_num(sell.get("lot"))
                    total_lot = buy_lot + sell_lot
                    br = (buy_lot / total_lot) if total_lot > 0 else None
                    pb_rows.append({
                        "symbol": sym,
                        "buy_lot": buy_lot,
                        "sell_lot": sell_lot,
                        "total_lot": total_lot,
                        "buy_ratio": br,
                    })
                time.sleep(0.15)
            except Exception:
                # skip simbol bermasalah
                pass

        if not pb_rows:
            lines.append("  (tidak ada data)")
        else:
            # urutkan by total lot desc
            pb_rows.sort(key=lambda r: r["total_lot"], reverse=True)
            lines.append("  Symbol  |  Buy%  |   Buy Lot   |  Sell Lot   |  Total Lot")
            lines.append("  --------+--------+-------------+-------------+------------")
            for r in pb_rows:
                sym = r["symbol"]
                br  = f"{r['buy_ratio']*100:5.1f}%" if r["buy_ratio"] is not None else "  n/a"
                bl  = id_int(r["buy_lot"])
                sl  = id_int(r["sell_lot"])
                tl  = id_int(r["total_lot"])
                lines.append(f"  {sym:<7} | {br:>6} | {bl:>11} | {sl:>11} | {tl:>10}")

    # Kirim / print
    tg_send("\n".join(lines))

if __name__ == "__main__":
    run()
