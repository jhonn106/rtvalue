# runners/rt_alerts.py (cuplikan)
import time
from datetime import datetime, timedelta
from clients import stockbit
from auth.stockbit_login import get_bearer_token

def run_loop():
    while _within_trading_window():  # fungsi window-mu
        try:
            data = stockbit.running_trade(limit=100)
            # ... proses & kirim telegram ...
        except RuntimeError as e:
            s = str(e)
            if "UNAUTHORIZED" in s or "401" in s or "403" in s:
                print("[RT ALERT] Unauthorized, refreshing token...")
                try:
                    get_bearer_token(force_refresh=True)
                except Exception as ee:
                    print("[RT ALERT] Refresh failed:", ee)
                time.sleep(2)
                continue   # coba lagi
            else:
                print("[RT ALERT] error:", s)
                # jangan mati—tunda sebentar lalu lanjut
                time.sleep(3)
                continue

        time.sleep(2)  # jeda polling 2 detik (atau sesuai kebutuhan)

if __name__ == "__main__":
    run_loop()
