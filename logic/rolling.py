def rupiah(n):
    try:
        return f"Rp{int(n):,}".replace(",", ".")
    except Exception:
        return str(n)

def _iter_items(payload):
    """
    Kembalikan iterator list item dari berbagai bentuk:
    - {"data": [...]}
    - {"data": {"items": [...]}}
    - {"result": [...]}
    - {"result": {"items": [...]}}
    - atau langsung list
    """
    if isinstance(payload, list):
        yield from payload
        return
    if not isinstance(payload, dict):
        return

    for topkey in ("data", "result"):
        v = payload.get(topkey)
        if isinstance(v, list):
            yield from v
            return
        if isinstance(v, dict):
            if isinstance(v.get("items"), list):
                yield from v["items"]
                return
            # kadang nested lagi
            for k, vv in v.items():
                if isinstance(vv, dict) and isinstance(vv.get("items"), list):
                    yield from vv["items"]
                    return

    # fallback: kalau ada key "items" di root
    if isinstance(payload.get("items"), list):
        yield from payload["items"]

def parse_market_mover(resp):
    """
    Normalisasi item market-mover → list dict:
      {'symbol','name','chg_pct','value','raw'}
    """
    items = []
    for it in _iter_items(resp):
        if not isinstance(it, dict):
            continue
        sym = it.get("symbol") or it.get("stock") or it.get("code")
        if not sym:
            continue
        name = it.get("name") or it.get("company_name") or ""
        chg  = it.get("change_percent") or it.get("chg_pct") or it.get("percentageChange")
        val  = it.get("value") or it.get("traded_value") or it.get("total_value")
        items.append({
            "symbol": sym,
            "name": name,
            "chg_pct": chg,
            "value": val,
            "raw": it
        })
    return items
