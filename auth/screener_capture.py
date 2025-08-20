# auth/screener_capture.py
import re
from playwright.sync_api import sync_playwright
from datetime import datetime, timezone

from auth.stockbit_login import get_bearer_token  # memastikan login/ bearer siap

SCREENER_URL = "https://stockbit.com/screener"
EXODUS_HOST = "exodus.stockbit.com"

def get_screener_results_by_name(name: str = "akum ihsg", headless: bool = True, timeout_ms: int = 45000):
    """
    Buka halaman /screener, pilih template (mis. 'Akum IHSG'), lalu ambil payload hasil
    dari XHR ke exodus /screener/results. Mengembalikan dict JSON hasil.

    name: teks yang muncul di UI Screener (case-insensitive).
    """
    # pastikan bearer valid (akan refresh jika perlu)
    _ = get_bearer_token()

    name_pat = re.compile(re.escape(name), re.I)
    last_payload = {"_source": "playwright_capture", "data": None, "_meta": {}}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(locale="id-ID")
        page = context.new_page()

        # hook response untuk menangkap hasil screener
        def on_response(resp):
            try:
                url = resp.url or ""
                if (EXODUS_HOST in url) and ("/screener/results" in url):
                    # ini biasanya payload hasil
                    j = resp.json()
                    last_payload["data"] = j
                    last_payload["_meta"] = {
                        "status": resp.status,
                        "url": url,
                        "ts": datetime.now(timezone.utc).isoformat()
                    }
            except Exception:
                pass

        context.on("response", on_response)

        # buka screener
        page.goto(SCREENER_URL, wait_until="domcontentloaded", timeout=timeout_ms)

        # cari kartu/row dengan teks "Akum IHSG" (case-insensitive)
        # beberapa varian UI:
        locs = [
            page.get_by_text(name, exact=False),
            page.locator("css=[class*=card], [class*=row], [data-testid*=screener], a, button").filter(has_text=name),
        ]

        clicked = False
        for loc in locs:
            try:
                # tunggu terlihat & klik
                loc.first.wait_for(state="visible", timeout=5000)
                loc.first.click(timeout=5000)
                clicked = True
                break
            except Exception:
                continue

        if not clicked:
            browser.close()
            raise RuntimeError(f"Tidak menemukan template screener dengan teks: {name!r}")

        # setelah klik, UI biasanya memicu XHR ke exodus/screener/results
        # tunggu network idle / sebentar agar response tersambar hook
        page.wait_for_load_state("networkidle", timeout=timeout_ms)

        # kalau belum dapat, beri sedikit waktu polling
        for _ in range(10):
            if last_payload["data"] is not None:
                break
            page.wait_for_timeout(500)

        browser.close()

    if last_payload["data"] is None:
        raise RuntimeError(f"Gagal menangkap hasil screener untuk {name!r}. Ubah kata kunci atau perpanjang timeout.")

    return last_payload
