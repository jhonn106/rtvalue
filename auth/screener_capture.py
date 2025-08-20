# auth/screener_capture.py
import os
import re
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

from auth.stockbit_login import get_bearer_token
from clients import stockbit  # untuk direct call ke exodus jika template_id tersedia

SCREENER_URL = "https://stockbit.com/screener"
EXODUS_HOST = "exodus.stockbit.com"

def get_screener_results_by_name(
    name: str | None = None,
    headless: bool = True,
    timeout_ms: int = 45000,
    template_id: int | None = None,
):
    """
    Ambil hasil screener:
      - Jika template_id ada -> coba langsung call exodus /screener/results (GET/POST ...).
      - Jika gagal/None -> buka /screener lalu klik radio/kartu sesuai 'name' (case-insensitive),
        kemudian tangkap XHR ke /screener/results.
    Return dict: {"_source": "...", "data": <json results>, "_meta": {...}}
    """
    # pastikan bearer valid
    _ = get_bearer_token()

    # ===== jalur 1: direct API pakai template_id =====
    if template_id:
        try:
            bundle = stockbit.akumulasi_results_any(template_id=template_id)
            j = bundle.get("data")
            if isinstance(j, (dict, list)):
                return {
                    "_source": f"direct_api_template_id={template_id}",
                    "data": j,
                    "_meta": {"ts": datetime.now(timezone.utc).isoformat()},
                }
        except Exception:
            # lanjut ke jalur klik
            pass

    # ===== jalur 2: Playwright klik di halaman /screener =====
    # kalau name tidak diberikan, pakai default "akum ihsg"
    if not name:
        name = "akum ihsg"

    name_pat = re.compile(re.escape(name), re.I)
    last_payload = {"_source": "playwright_capture", "data": None, "_meta": {}}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(locale="id-ID")
        page = context.new_page()

        # hook response untuk tangkap /screener/results
        def on_response(resp):
            try:
                url = resp.url or ""
                if (EXODUS_HOST in url) and ("/screener/results" in url):
                    j = resp.json()
                    last_payload["data"] = j
                    last_payload["_meta"] = {
                        "status": resp.status,
                        "url": url,
                        "ts": datetime.now(timezone.utc).isoformat(),
                    }
            except Exception:
                pass

        context.on("response", on_response)

        page.goto(SCREENER_URL, wait_until="domcontentloaded", timeout=timeout_ms)

        # ==== beberapa strategi klik sesuai markup yang kamu kirim ====
        # 1) label radio: <label class="ant-radio-button-wrapper ..."><span>akum ihsg</span></label>
        selectors = [
            # label radio Ant Design dengan teks
            f"label.ant-radio-button-wrapper:has-text('{name}')",
            # elemen apapun yang mengandung teks (fallback)
            f"css=[class*='radio'], [class*='card'], [role='radio'], button, a, label:has-text('{name}')",
        ]

        clicked = False
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                loc.wait_for(state="visible", timeout=5000)
                loc.click(timeout=5000, force=True)
                clicked = True
                break
            except Exception:
                continue

        # 2) Kalau masih gagal, dan ada template_id -> klik input radio by value
        if (not clicked) and template_id:
            try:
                inp = page.locator(f"input.ant-radio-button-input[value='{template_id}']").first
                inp.wait_for(state="attached", timeout=5000)
                # klik label terdekat
                page.evaluate(
                    """(el)=>{ el.closest('label')?.click(); }""",
                    inp,
                )
                clicked = True
            except Exception:
                pass

        if not clicked:
            browser.close()
            raise RuntimeError(f"Tidak menemukan template screener dengan teks: {name!r}")

        # tunggu XHR /screener/results tertangkap
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
        for _ in range(10):
            if last_payload["data"] is not None:
                break
            page.wait_for_timeout(500)

        browser.close()

    if last_payload["data"] is None:
        raise RuntimeError(f"Gagal menangkap hasil screener untuk {name!r}. Pertimbangkan set template_id.")

    return last_payload
