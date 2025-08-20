def rupiah(n):
    try:
        return f"Rp{int(n):,}".replace(",", ".")
    except Exception:
        return str(n)

def parse_market_mover(resp):
    items = []
    data = resp.get("data") if isinstance(resp, dict) else resp
    if isinstance(data, list):
        for it in data:
            sym = it.get("symbol") or it.get("stock") or it.get("code")
            items.append({
                "symbol": sym,
                "name": it.get("name") or "",
                "chg_pct": it.get("change_percent") or it.get("chg_pct"),
                "value": it.get("value") or it.get("traded_value"),
                "raw": it,
            })
    return [x for x in items if x["symbol"]]
