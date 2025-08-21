# clients/stockbit.py
import os, time, requests
from auth.stockbit_login import get_bearer_token

# Optional import: pakai untuk refresh paksa saat 401/403
try:
    from auth.stockbit_login import login_and_capture_token
except ImportError:
    login_and_capture_token = None

TOKEN_PATH = os.environ.get("STOCKBIT_TOKEN_PATH", "token.json")

def _headers():
    bearer = get_bearer_token()  # ambil dari env/token.json
    return {
        "Authorization": f"Bearer {bearer}",
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Origin": "https://stockbit.com",
        "Referer": "https://stockbit.com/stream",
        "Connection": "keep-alive",
    }

def _request_with_refresh(method, url, params=None, json=None, timeout=30):
    # attempt #1
    r = requests.request(method, url, params=params, json=json, headers=_headers(), timeout=timeout)

    # kalau unauthorized → paksa refresh via login_and_capture_token → retry sekali
    if r.status_code in (401, 403) and login_and_capture_token:
        try:
            print("[AUTH] Unauthorized; refreshing token via login_and_capture_token() …")
            login_and_capture_token(headless=True)
            time.sleep(1.0)
            r = requests.request(method, url, params=params, json=json, headers=_headers(), timeout=timeout)
        except Exception as e:
            print("[AUTH] Refresh failed:", e)

    if r.status_code >= 400:
        raise RuntimeError(f"GET failed: {url} {r.text}")
    return r

def _get(url, params=None):
    return _request_with_refresh("GET", url, params=params).json()

def _post(url, payload=None):
    return _request_with_refresh("POST", url, json=payload).json()

# contoh endpoint
def running_trade(limit=50, sort="DESC", order_by="RUNNING_TRADE_ORDER_BY_TIME"):
    url = "https://exodus.stockbit.com/order-trade/running-trade"
    q = [("sort", sort), ("order_by", order_by), ("limit", str(limit))]
    return _get(url, params=q)
