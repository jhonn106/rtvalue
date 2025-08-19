import time, requests
from clients.token_store import ensure_bearer

BASE = "https://exodus.stockbit.com"
UA = "Mozilla/5.0 (compatible; StockbitBot/1.0)"

def _headers():
    token = ensure_bearer()
    return {
        "authorization": f"Bearer {token}",
        "accept": "application/json, text/plain, */*",
        "user-agent": UA,
    }

def _get(url, params=None, tries=3, backoff=1.5, timeout=12):
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, headers=_headers(), params=params, timeout=timeout)
            if r.status_code == 200:
                return r.json()
            last = (r.status_code, r.text[:200])
        except Exception as e:
            last = e
        time.sleep(backoff ** i)
    raise RuntimeError(f"GET failed: {url} {last}")

def top_gainer():
    url = f"{BASE}/order-trade/market-mover"
    q = [("mover_type","MOVER_TYPE_TOP_GAINER")]
    for f in [
        "FILTER_STOCKS_TYPE_MAIN_BOARD",
        "FILTER_STOCKS_TYPE_DEVELOPMENT_BOARD",
        "FILTER_STOCKS_TYPE_ACCELERATION_BOARD",
        "FILTER_STOCKS_TYPE_NEW_ECONOMY_BOARD",
    ]:
        q.append(("filter_stocks", f))
    return _get(url, params=q)

def top_value():
    url = f"{BASE}/order-trade/market-mover"
    q = [("mover_type","MOVER_TYPE_TOP_VALUE")]
    for f in [
        "FILTER_STOCKS_TYPE_MAIN_BOARD",
        "FILTER_STOCKS_TYPE_DEVELOPMENT_BOARD",
        "FILTER_STOCKS_TYPE_ACCELERATION_BOARD",
        "FILTER_STOCKS_TYPE_NEW_ECONOMY_BOARD",
    ]:
        q.append(("filter_stocks", f))
    return _get(url, params=q)

def running_trade(limit=50):
    url = f"{BASE}/order-trade/running-trade"
    params = {"sort":"DESC","order_by":"RUNNING_TRADE_ORDER_BY_TIME","limit":limit}
    return _get(url, params=params)

def powerbuy(symbol, interval="10m"):
    url = f"{BASE}/order-trade/trade-book"
    params = {"symbol":symbol,"group_by":"GROUP_BY_TIME","time_interval":interval}
    return _get(url, params=params)
