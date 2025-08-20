# auth/screener_capture.py
import os, re, json
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

from auth.stockbit_login import get_bearer_token
from clients import stockbit

SCREENER_URL = "https://stockbit.com/screener"
EXODUS_HOST = "exodus.stockbit.com"

def get_screener_results_by_name(
    name: str | None = None,
    headless: bool = True,
    timeout_ms: int = 60000,
    template_id: int | None = None,
    per_page: int = 2000,
    debug: bool = False,
    debug_dir: str = "data/bandar/raw",
):
    """
    Langkah:
      1) Kalau template_id ada -> tembak API /screener/results (GET/POST)
      2) Kalau gagal -> buka /screener, klik radio/label sesuai name atau input[value] template_id,
         lalu tunggu response /screener/results via wait_for_response.
    Return: {"_source": "...", "data": <json>, "_meta": {...}}
    """
    # pastikan bearer valid
    _ = get_bearer_token()

    # 1) direct API pakai template_id
    if template_id:
        try:
            bundle = stockbit.akumulasi_results_any(template_id=template_id, per_page=per_page)
            j = bundle.get("data")
            if isinstance(j, (dict, list)):
                return {
                    "_source": f"direct_api_template_id={template_id}",
                    "data": j,
                    "_meta": {"ts": datetime.now(timezone.utc).isoformat()},
                }
        except Exception:
            pass  # lanjut ke Playwright

    # 2) Playwright capture
    if not name:
        name = "akum ihsg"

    last_payload = None

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        context = pw.chromium.launch_persistent_context(
            user_data_dir="/tmp/sb_ud",
            headless=headless,
            locale="id-ID",
        ) if False else browser.new_context(locale="id-ID")
        page = context.new_page()

        page.goto(SCREENER_URL, wait_until="domcontentloaded", timeout=timeout_ms)

        # klik via selector akurat:
        clicked = False
        # a) input radio by value (kalau kita tahu template_id)
        if template_id and not clicked:
            try:
                inp = page.locator(f"input.ant-radio-button-input[value='{template_id}']").first
                inp.wait_for(state="attached", timeout=5000)
                page.evaluate("""(el)=>{ el.closest('label')?.scrollIntoView(); }""", inp)
                page.evaluate("""(el)=>{ el.closest('label')?.click(); }""", inp)
                clicked = True
            except Exception:
                pass

        # b) label ant-radio-button-wrapper:has-text("akum ihsg")
        if not clicked:
            try:
                sel = f"label.ant-radio-button-wrapper:has-text('{name}')"
                loc = page.locator(sel).first
                loc.wait_for(state="visible", timeout=5000)
                loc.scroll_into_view_if_needed(timeout=3000)
                loc.click(timeout=5000, force=True)
                clicked = True
            except Exception:
                pass

        # c) fallback generic
        if not clicked:
            try:
                sel = f"label:has-text('{name}'), [role='radio']:has-text('{name}'), [class*='radio']:has-text('{name}')"
                loc = page.locator(sel).first
                loc.wait_for(state="visible", timeout=5000)
                loc.click(timeout=5000, force=True)
                clicked = True
            except Exception:
                pass

        if not clicked:
            browser.close()
            raise RuntimeError(f"Tidak menemukan template screener dengan teks: {name!r}")

        # tunggu response /screener/results
        def _matcher(resp):
            url = resp.url or ""
            return (EXODUS_HOST in url) and ("/screener/results" in url) and resp.status == 200

        try:
            resp = page.wait_for_response(_matcher, timeout=timeout_ms)
            j = resp.json()
            last_payload = {
                "_source": "playwright_capture",
                "data": j,
                "_meta": {
                    "status": resp.status,
                    "url": resp.url,
                    "ts": datetime.now(timezone.utc).isoformat(),
                },
            }
        except Exception as e:
            # ambil screenshot untuk debug
            if debug:
                os.makedirs(debug_dir, exist_ok=True)
                ss = os.path.join(debug_dir, "screener_fail.png")
                page.screenshot(path=ss, full_page=True)
            browser.close()
            raise RuntimeError(f"Gagal menangkap /screener/results via Playwright: {e}")

        if debug:
            os.makedirs(debug_dir, exist_ok=True)
            page.screenshot(path=os.path.join(debug_dir, "screener_ok.png"), full_page=True)

        browser.close()

    if not last_payload:
        raise RuntimeError(f"Gagal menangkap hasil screener untuk {name!r} (no payload).")

    return last_payload
