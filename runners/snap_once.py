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
