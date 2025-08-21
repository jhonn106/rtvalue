# clients/stockbit.py (helper request dengan auto-refresh saat 401/403)
import requests, time
from auth.stockbit_login import get_bearer_token
from auth.stockbit_login import login_and_capture_token  # pastikan ada

def _headers():
    bearer = get_bearer_token()
    return {
        "Authorization": f"Bearer {bearer}",
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome Safari",
        "Origin": "https://stockbit.com",
        "Referer": "https://stockbit.com/stream",
        "Connection": "keep-alive",
    }

def _request_with_refresh(method, url, params=None, json=None, timeout=30):
    r = requests.request(method, url, params=params, json=json, headers=_headers(), timeout=timeout)
    if r.status_code in (401, 403):
        # paksa login ulang
        try:
            login_and_capture_token(headless=True)
            time.sleep(1.0)
        except Exception as e:
            print("[AUTH] hard refresh failed:", e)
        # retry
        r = requests.request(method, url, params=params, json=json, headers=_headers(), timeout=timeout)

    if r.status_code >= 400:
        raise RuntimeError(f"GET failed: {url} {r.text}")
    return r
