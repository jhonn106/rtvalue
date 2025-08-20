def rupiah(n):
    try:
        return f"Rp{int(float(n)):,}".replace(",", ".")
    except Exception:
        return str(n)

def _iter_items(payload):
    """
    Normalisasi berbagai bentuk:
    - {"data": {"mover_list": [...]}}
    - {"data": {"items": [...]}} / {"result": {"items": [...]}}
    - {"data": [...]} / {"result": [...]}
    - langsung list
    """
    if isinstance(payload, list):
        for it in payload:
            yield it
        return
    if not isinstance(payload, dict):
        return

    # Jalur baru Stockbit: data.mover_list
    d = payload.get("data")
    if isinstance(d, dict) and isinstance(d.get("mover_list"), list):
        for it in d["mover_list"]:
            yield it
        return

    # Varian umum sebelumnya
    for top in ("data", "result"):
        v = payload.get(top)
        if isinstance(v, list):
            for it in v:
                yield it
            return
        if isinstance(v, dict):
            if isinstance(v.get("items"), list):
                for it in v["items"]:
                    yield it
                return
            # nested.items
            for _, vv in v.items():
                if isinstance(vv, dict) and isinstance(vv.get("items"), list):
                    for it in vv["items"]:
                        yield it
                    return

    # Root items
    if isinstance(payload.get("items"), list):
        for it in payload["items"]:
            yield it

def parse_market_mover(resp):
    """
    Kembalikan list:
      {'symbol','name','chg_pct','value','raw'}
    Support struktur baru (data.mover_list).
    """
    out = []
    for it in _iter_items(resp):
        if not isinstance(it, dict):
            continue

        # Struktur baru:
        sd = it.get("stock_detail") or {}
        sym = sd.get("code") or it.get("symbol") or it.get("stock") or it.get("code")
        if not sym:
            continue
        name = sd.get("name") or it.get("name") or ""
        chg  = None
        ch = it.get("change")
        if isinstance(ch, dict):
            chg = ch.get("percentage")  # sudah dalam persen, contoh: 34.44
        if chg is None:
            chg = it.get("change_percent") or it.get("chg_pct") or it.get("percentageChange")

        val = None
        vv = it.get("value")
        if isinstance(vv, dict) and "raw" in vv:
            val = vv["raw"]
        if val is None:
            val = it.get("value") or it.get("traded_value") or it.get("total_value")

        out.append({
            "symbol": sym,
            "name": name,
            "chg_pct": chg,
            "value": val,
            "raw": it
        })
    return out
