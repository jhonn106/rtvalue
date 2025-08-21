# runners/refresh_token.py
from auth.stockbit_login import get_bearer_token

# Coba import fungsi login paksa; kalau tidak ada, fallback ke get_bearer_token biasa
try:
    from auth.stockbit_login import login_and_capture_token
except ImportError:
    login_and_capture_token = None

if __name__ == "__main__":
    tok = None
    if login_and_capture_token:
        # Paksa login via Playwright untuk memastikan token fresh dan tersimpan ke token.json
        tok = login_and_capture_token(headless=True)
        print("✅ Token refreshed via login_and_capture_token. Prefix:", tok[:16], "...")
    else:
        # Fallback: minimal pastikan bisa ambil token yang berlaku (tanpa paksa refresh)
        tok = get_bearer_token()
        print("ℹ️ login_and_capture_token() not found; used get_bearer_token(). Prefix:", tok[:16], "...")
