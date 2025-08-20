import os, json, csv, time
from datetime import datetime, timedelta
from pathlib import Path
import pytz
import requests

from clients import stockbit

# ================= Konfigurasi =================
TZ = pytz.timezone("Asia/Jakarta")

DATA_DIR = Path("data/bandar")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# kirim ke bot Telegram #3 (pisah dari bot snapshot/rt)
TG_TOKEN = os.environ.get("TG_TOKEN") or os.environ.get("TG_TOKEN_BANDAR")
TG_CHAT_ID3 = os.environ.get("TG_CHAT_ID3")


MAX_SYMBOLS = 20   # kirim maksimal 20 saham
ROLLING_DAYS = 5   # kumpulkan 5 hari (Senin–Sabtu)

# ===============================================

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
    """
    Implementasi ekuivalen dari:
    =IF(C2>30,"3BA",
      IF(C2<-30,"3BD",
        IF(AND(C2>=20,C2<30),"2BA",
          IF(AND(C2>=10,C2<20),"1BA",
            IF(AND(C2=0),"No",
              IF(AND(C2>-20,C2<-10),"1BD",
                IF(AND(C2>-30,C2<-20),"2BD",
                  IF(AND(C2>-10,C2<0),"ND",
                    IF(AND(C2>0,C2<10),"NA","nan")))))))))
    """
    try:
        v = float(x)
    except Exception:
        return "nan"
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

def _parse_akumulasi(resp):
    """
    Normalisasi output API ke list: [{'symbol': 'BBCA', 'value': <float>}]
    Struktur umum screener: {"data": {"rows": [{"symbol": "...", "value": 12.3}, ...]}}
    tapi kita buat robust.
    """
    out = []
    if isinstance(resp, dict):
        d = resp.get("data") or resp.get("result") or {}
        rows = None
        # beberapa screener menyimpan di "rows" atau langsung list
        if isinstance(d, dict):
            for k in ("rows", "items", "list"):
                if isinstance(d.get(k), list):
                    rows = d.get(k)
                    break
            if rows is None and isinstance(d.get("data"), list):
                rows = d.get("data")
        if rows is None and isinstance(resp.get("rows"), list):
            rows = resp.get("rows")
        if rows is None and isinstance(resp.get("items"), list):
            rows = resp.get("items")
        if rows is None and isinstance(resp.get("list"), list):
            rows = resp.get("list")
        if rows is None and isinstance(resp.get("data"), list):
            rows = resp.get("data")

        if isinstance(rows, list):
            for r in rows:
                if not isinstance(r, dict): 
                    continue
                sym = r.get("symbol") or r.get("code") or r.get("stock") or r.get("ticker")
                # field nilai akumulasi – coba beberapa nama
                val = r.get("value")
                if val is None:
                    val = r.get("akum") or r.get("accum") or r.get("score") or r.get("C") or r.get("c")
                if not sym: 
                    continue
                try:
                    val = float(val)
                except Exception:
                    continue
                out.append({"symbol": sym, "value": val})
    elif isinstance(resp, list):
        for r in resp:
            if isinstance(r, dict) and r.get("symbol") and r.get("value") is not None:
                try:
                    out.append({"symbol": r["symbol"], "value": float(r["value"])})
                except Exception:
                    pass
    return out

def _save_csv_daily(day_path_csv: Path, rows):
    with day_path_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["symbol","value","class"])
        for r in rows:
            w.writerow([r["symbol"], r["value"], _classify(r["value"])])

def _date_range_last_n(n_days: int, end_date: datetime):
    """Hasilkan list tanggal (YYYY-MM-DD) mundur n hari kalendar (termasuk end_date)."""
    out = []
    for i in range(n_days):
        d = (end_date - timedelta(days=i)).date().isoformat()
        out.append(d)
    return out  # [YYYY-MM-DD, kemarin, dst]

def _sum_rolling_5d():
    """
    Baca file harian 5 hari terakhir → jumlahkan value per symbol,
    sekalian simpan class untuk hari TERAKHIR (opsional).
    """
    today = now_id()
    dates = _date_range_last_n(ROLLING_DAYS, today)
    acc = {}
    last_class = {}  # class terbaru (hari terakhir tersedia)
    for ds in dates:
        day_json = DATA_DIR / f"{ds}.json"
        rows = _read_json(day_json, default=[])
        if not isinstance(rows, list):
            continue
        for r in rows:
            sym = r.get("symbol")
            val = r.get("value")
            if sym is None or val is None:
                continue
            try:
                v = float(val)
            except Exception:
                continue
            acc[sym] = acc.get(sym, 0.0) + v
            last_class[sym] = _classify(v)  # class per-hari (opsional)
    # hasil: list dict
    out = []
    for sym, total in acc.items():
        out.append({"symbol": sym, "total_value": total})
    # urut desc by total_value
    out.sort(key=lambda x: x["total_value"], reverse=True)
    return out

def _rupiah(n):
    try:
        return f"Rp{int(n):,}".replace(",", ".")
    except Exception:
        return str(n)

def main():
    # 1) ambil data akumulasi dari API
    resp = stockbit.akumulasi_custom()
    rows = _parse_akumulasi(resp)

    # 2) simpan harian (json+csv)
    ds = now_id().date().isoformat()
    day_json = DATA_DIR / f"{ds}.json"
    day_csv  = DATA_DIR / f"{ds}.csv"
    _save_json(day_json, rows)
    _save_csv_daily(day_csv, rows)

    # 3) hitung rolling 5 hari
    roll = _sum_rolling_5d()

    # 4) filter kategori (3BA & 2BA) berdasarkan nilai HARI INI untuk label,
    #    tapi ranking tetap pakai total 5D
    #    – kalau mau kategori berdasarkan total (rata-rata harian), tinggal diganti logikanya.
    today_map = {r["symbol"]: r["value"] for r in rows}
    def _class_today(sym):
        v = today_map.get(sym)
        return _classify(v) if v is not None else "nan"

    # Ambil hanya 3BA & 2BA, lalu top-N by total_value
    filt = [r for r in roll if _class_today(r["symbol"]) in ("3BA","2BA")]
    top = filt[:MAX_SYMBOLS]

    # 5) kirim ke Telegram
    title = f"📊 Bandar Accumulation 5D (per {ds}) — Kategori 3BA & 2BA (Top {MAX_SYMBOLS})"
    lines = [title, ""]
    rank = 1
    for r in top:
        sym = r["symbol"]
        tot = r["total_value"]
        cls = _class_today(sym)
        lines.append(f"{rank}. {sym:<6} {tot:+.2f}  [{cls}]")
        rank += 1

    if len(top) == 0:
        lines.append("(tidak ada saham kategori 3BA/2BA hari ini)")
    msg = "\n".join(lines)
    _send_tg(msg)

    # 6) simpan ringkasan rolling_5d
    roll_path = DATA_DIR / "rolling_5d.json"
    _save_json(roll_path, {"date": ds, "top": top, "count_all": len(roll)})

if __name__ == "__main__":
    main()
