# clients/stockbit.py
import os, time, requests
from auth.stockbit_login import get_bearer_token

TOKEN_PATH = os.environ.get("STOCKBIT_TOKEN_PATH", "token.json")

def _headers():
    bearer = get_bearer_token()  # ambil dari env/token.json; auto-refresh kalau hampir kadaluarsa
    return {
        "Authorization": f"Bearer {bearer}",
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Origin": "https://stockbit.com",
        "Referer": "https://stockbit.com/stream",  # referer valid
        "Connection": "keep-alive",
    }

def _request_with_refresh(method, url, params=None, json=None, timeout=30):
    # attempt 1
    r = requests.request(method, url, params=params, json=json, headers=_headers(), timeout=timeout)
    if r.status_code in (401, 403):
        # paksa refresh token lalu retry sekali
        try:
            get_bearer_token(force_refresh=True)  # LOG IN ulang via Playwright & simpan token baru
            time.sleep(1.0)
        except Exception:
            pass
        r = requests.request(method, url, params=params, json=json, headers=_headers(), timeout=timeout)

    if r.status_code >= 400:
        # kirim body supaya mudah didiagnosa di log
        raise RuntimeError(f"GET failed: {url} {r.text}")
    return r

def _get(url, params=None):
    return _request_with_refresh("GET", url, params=params).json()

def _post(url, payload=None):
    return _request_with_refresh("POST", url, json=payload).json()

# --- contoh pemakaian yang sudah ada ---
def running_trade(limit=50, sort="DESC", order_by="RUNNING_TRADE_ORDER_BY_TIME"):
    url = "https://exodus.stockbit.com/order-trade/running-trade"
    q = [("sort", sort), ("order_by", order_by), ("limit", str(limit))]
    return _get(url, params=q)

# ... fungsi top_gainer, top_value, powerbuy, dst tetap sama tapi gunakan _get/_post di atas ...
