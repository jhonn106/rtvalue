import os, time, json, requests

BASE = "https://exodus.stockbit.com"

from auth.token_manager import manager as token_manager

def _headers():
    tok = token_manager.get_token()
    return {
        "authorization": f"Bearer {tok}",
        "accept": "application/json, text/plain, */*",
        "user-agent": "Mozilla/5.0 (compatible; StockbitBot/1.0)",
        "origin": "https://stockbit.com",
        "referer": "https://stockbit.com/",
    }

def _request_with_refresh(method, url, **kwargs):
    """
    Kirim request. Kalau 401 → refresh token → retry sekali.
    """
    # try once
    r = requests.request(method, url, headers=_headers(), timeout=20, **kwargs)
    if r.status_code != 401:
        return r
    # token mungkin kadaluarsa → refresh & retry
    try:
        token_manager.refresh()
    except Exception:
        pass
    r2 = requests.request(method, url, headers=_headers(), timeout=20, **kwargs)
    return r2

def _get(url, params=None):
    last = None
    try:
        r = _request_with_refresh("GET", url, params=params)
        last = r.text[:200]
        r.raise_for_status()
        return r.json()
    except Exception as e:
        raise RuntimeError(f"GET failed: {url} {last}") from e

# === API convenience ===

def top_gainer():
    url = f"{BASE}/order-trade/market-mover"
    q = [("mover_type","MOVER_TYPE_TOP_GAINER")]
    return _get(url, params=q)

def top_value():
    url = f"{BASE}/order-trade/market-mover"
    q = [("mover_type","MOVER_TYPE_TOP_VALUE")]
    return _get(url, params=q)

def top_gainer_simple():
    return top_gainer()

def top_value_simple():
    return top_value()

def running_trade(limit=50):
    url = f"{BASE}/order-trade/running-trade"
    q = [("sort","DESC"), ("order_by","RUNNING_TRADE_ORDER_BY_TIME"), ("limit", str(limit))]
    return _get(url, params=q)

def running_trade_simple():
    url = f"{BASE}/order-trade/running-trade"
    return _get(url, params=None)

def powerbuy(symbol, interval="10m"):
    url = f"{BASE}/order-trade/trade-book"
    q = [("symbol", symbol), ("group_by","GROUP_BY_TIME"), ("time_interval", interval)]
    return _get(url, params=q)

def akumulasi_custom():
    """
    Ambil data akumulasi dari screener kustom.
    Hasil: JSON (server-side), nanti di-parse di runner.
    """
    url = "https://exodus.stockbit.com/screener/templates/4272542"
    q = [("type", "TEMPLATE_TYPE_CUSTOM")]
    return _get(url, params=q)

