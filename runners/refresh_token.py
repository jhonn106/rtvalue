# runners/refresh_token.py
from auth.stockbit_login import get_bearer_token

if __name__ == "__main__":
    # Paksa login ulang & simpan token.json baru
    tok = get_bearer_token(force_refresh=True)
    print("✅ Token refreshed. Prefix:", tok[:16], "...")
