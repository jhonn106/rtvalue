import os, json, csv, time
from datetime import datetime, timedelta
from pathlib import Path
import pytz
import requests

from clients import stockbit

# ================= Konfigurasi =================
TZ = pytz.timezone("Asia/Jakarta")

DATA_DIR = Path("data/bandar")
RAW_DIR = DATA_DIR / "raw"
DATA_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)

TG_TOKEN = os.environ.get("TG_TOKEN") or os.environ.get("TG_TOKEN_BANDAR")
TG_CHAT_ID3 = os.environ.get("TG_CHAT_ID3") or os.environ.get("BANDAR_TG_CHAT_ID")

MAX_SYMBOLS = 20
ROLLING_DAYS = 5
API_RETRIES = 3
API_SLEEP = 2  # detik antar-retry

def now_id():
    return datetime.now(TZ)

def _save_json(path: Path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def _read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def _send_tg(text: str):
    if not TG_TOKEN or not TG_CHAT_ID3:
        print("[BANDAR]", text)
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT_ID3, "text": text, "parse_mode": "HTML"},
            timeout=20,
        )
        if r.status_code != 200:
            print("[BANDAR WARN]", r.text)
    except Exception as e:
        print("[BANDAR ERR]", e)

def _classify(x):
    try: v = float(x)
    except Exception: return "nan"
    if v > 30: return "3BA"
    if v < -30: return "3BD"
    if 20 <= v < 30: return "2BA"
    if 10 <= v < 20: return "1BA"
    if v == 0: return "No"
    if -20 < v < -10: return "1BD"
    if -30 < v < -20: return "2BD"
    if -10 < v < 0: return "ND"
    if 0 < v < 10: return "NA"
    return "nan"

def _norm_symbol(x):
    if not x: return None
    s = str(x).strip().upper()
    # hapus spasi aneh
    return "".join(ch for ch in s if ch.isalnum())

def _parse_akumulasi(resp):
    """
    Kembalikan list [{'symbol': 'BBCA', 'value': float}, ...]
    Dukung beberapa bentuk:
      A) {"data":{"rows":[{"symbol":"BBCA","value":12.3}, ...]}}
      B) {"data":{"columns":["symbol","value"],"rows":[["BBCA",12.3], ...]}}
      C) {"rows":[...]} atau {"items":[...]} atau list langsung
    """
    out = []

    def _try_rows(rows):
        nonlocal out
        if not isinstance(rows, list): return
        # kasus dict per baris
        if rows and isinstance(rows[0], dict):
            for r in rows:
                sym = _norm_symbol(r.get("symbol") or r.get("code") or r.get("stock") or r.get("ticker"))
            #  tambahkan if within loop
                if not sym: continue
                val = r.get("value")
                if val is None: val = r.get("akum") or r.get("accum") or r.get("score") or r.get("C") or r.get("c")
                try:
                    out.append({"symbol": sym, "value": float(val)})
                except Exception:
                    continue
            return
        # kasus array per baris + columns
        # ini akan ditangani di luar pakai _try_table jika columns diketahui

    def _try_table(columns, rows):
        nonlocal out
        if not isinstance(columns, list) or not isinstance(rows, list): return
        # cari index kolom simbol & value
        cols = [str(c).lower() for c in columns]
        try:
            i_sym = next(i for i,c in enumerate(cols) if c in ("symbol","code","stock","ticker"))
        except StopIteration:
            return
        # value bisa "value","akum","accum","score","c"
        cand_vals = ("value","akum","accum","score","c")
        i_val = None
        for k in cand_vals:
            if k in cols:
                i_val = cols.index(k); break
        if i_val is None: return
        # parse
        for row in rows:
            if not isinstance(row, (list, tuple)): continue
            if len(row) <= max(i_sym, i_val): continue
            sym = _norm_symbol(row[i_sym])
            if not sym: continue
            try:
                out.append({"symbol": sym, "value": float(row[i_val])})
            except Exception:
                continue

    # mulai parse
    if isinstance(resp, dict):
        d = resp.get("data") or resp.get("result") or {}
        # bentuk A: rows dict
        for key in ("rows","items","list","data"):
            v = d.get(key)
            if isinstance(v, list):
                _try_rows(v)
        # bentuk B: columns + rows (tabel)
        cols = None; rows = None
        if isinstance(d, dict) and isinstance(d.get("columns"), list):
            cols = d.get("columns")
            # rows bisa di "rows" atau "data"
            rows = d.get("rows") if isinstance(d.get("rows"), list) else d.get("data")
            _try_table(cols, rows)
        # fallback di root
        if not out:
            for key in ("rows","items","list","data"):
                v = resp.get(key)
                if isinstance(v, list):
                    _try_rows(v)
    elif isinstance(resp, list):
        # list langsung, coba dict per-baris
        for r in resp:
            if isinstance(r, dict):
                sym = _norm_symbol(r.get("symbol") or r.get("code") or r.get("stock") or r.get("ticker"))
                if not sym: continue
                val = r.get("value")
                if val is None: val = r.get("akum") or r.get("accum") or r.get("score") or r.get("C") or r.get("c")
                try:
                    out.append({"symbol": sym, "value": float(val)})
                except Exception:
                    continue

    # hapus duplikat symbol, ambil terakhir
    uniq = {}
    for r in out:
        uniq[r["symbol"]] = r["value"]
    return [{"symbol": s, "value": v} for s,v in uniq.items()]

def _save_csv_daily(day_path_csv: Path, rows):
    with day_path_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["symbol","value","class"])
        for r in rows:
            w.writerow([r["symbol"], r["value"], _classify(r["value"])])

def _date_range_last_n(n_days: int, end_date: datetime):
    return [(end_date - timedelta(days=i)).date().isoformat() for i in range(n_days)]

def _sum_rolling_5d():
    today = now_id()
    dates = _date_range_last_n(ROLLING_DAYS, today)
    acc = {}
    for ds in dates:
        day_json = DATA_DIR / f"{ds}.json"
        rows = _read_json(day_json, default=[])
        if not isinstance(rows, list): continue
        for r in rows:
            sym = r.get("symbol"); val = r.get("value")
            if sym is None or val is None: continue
            try: v = float(val)
            except Exception: continue
            acc[sym] = acc.get(sym, 0.0) + v
    out = [{"symbol": s, "total_value": v} for s, v in acc.items()]
    out.sort(key=lambda x: x["total_value"], reverse=True)
    return out

def main():
    ds = now_id().date().isoformat()
    day_json = DATA_DIR / f"{ds}.json"
    day_csv  = DATA_DIR / f"{ds}.csv"
    raw_json = RAW_DIR / f"{ds}.raw.json"

    # 1) ambil data (retry) + simpan raw
    resp = None
    for i in range(API_RETRIES):
        try:
            resp = stockbit.akumulasi_custom()
            break
        except Exception as e:
            print("[BANDAR] fetch error:", e)
            time.sleep(API_SLEEP)
    if resp is None:
        _send_tg("⚠️ Bandar Nightly: gagal ambil data (resp=None).")
        return

    _save_json(raw_json, resp)  # simpan raw untuk debugging

    # 2) parse → rows
    rows = _parse_akumulasi(resp)
    print(f"[BANDAR] parsed rows = {len(rows)}")

    if not rows:
        # JANGAN overwrite file harian kalau kosong — kirim warning saja.
        _send_tg("⚠️ Bandar Nightly: data kosong dari screener. File harian tidak diupdate.")
        # Tetap update rolling_5d agar tidak error (pakai data sebelumnya)
        roll = _sum_rolling_5d()
        _save_json(DATA_DIR / "rolling_5d.json", {"date": ds, "top": roll[:MAX_SYMBOLS], "count_all": len(roll)})
        return

    # 3) simpan harian (json+csv)
    _save_json(day_json, rows)
    _save_csv_daily(day_csv, rows)

    # 4) rolling 5D dan filter kategori hari-ini (3BA/2BA)
    today_map = {r["symbol"]: r["value"] for r in rows}
    def _class_today(sym):
        v = today_map.get(sym)
        return _classify(v) if v is not None else "nan"

    roll = _sum_rolling_5d()
    filt = [r for r in roll if _class_today(r["symbol"]) in ("3BA","2BA")]
    top = filt[:MAX_SYMBOLS]

    # 5) kirim telegram ringkas (kalau mau versi panjang, mudah ditambah)
    title = f"📊 Bandar Accumulation 5D (per {ds}) — 3BA & 2BA (Top {MAX_SYMBOLS})"
    lines = [title, ""]
    if not top:
        lines.append("(tidak ada 3BA/2BA hari ini)")
    else:
        for i, r in enumerate(top, 1):
            sym = r["symbol"]; tot = r["total_value"]; cls = _class_today(sym)
            lines.append(f"{i}. {sym:<6} {tot:+.2f}  [{cls}]")
    _send_tg("\n".join(lines))

    # 6) simpan ringkasan rolling
    _save_json(DATA_DIR / "rolling_5d.json", {"date": ds, "top": top, "count_all": len(roll)})

if __name__ == "__main__":
    main()
