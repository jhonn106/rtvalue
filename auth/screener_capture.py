# auth/screener_capture.py
import os, re, json
from datetime import datetime, timezone
from typing import List
from playwright.sync_api import sync_playwright, Page, Frame

from auth.stockbit_login import get_bearer_token
from clients import stockbit  # untuk direct API

SCREENER_URL = "https://stockbit.com/screener"
EXODUS_HOST = "exodus.stockbit.com"

def _wait_results(page_or_frame, timeout_ms: int):
    def _matcher(resp):
        url = (resp.url or "")
        return (EXODUS_HOST in url) and ("/screener/results" in url) and resp.status == 200
    resp = page_or_frame.wait_for_response(_matcher, timeout=timeout_ms)
    return {"json": resp.json(), "url": resp.url, "status": resp.status}

def _click_in_frame(fr: Frame, name: str, template_id: int) -> bool:
    # 1) klik input radio by value (paling akurat jika ada)
    try:
        inp = fr.locator(f"input.ant-radio-button-input[value='{template_id}']").first
        inp.wait_for(state="attached", timeout=1500)
        fr.evaluate("""(el)=>{ el.closest('label')?.scrollIntoView(); }""", inp)
        fr.evaluate("""(el)=>{ el.closest('label')?.click(); }""", inp)
        return True
    except Exception:
        pass

    # 2) klik label ant-radio-button-wrapper yang punya teks
    try:
        sel = f"label.ant-radio-button-wrapper:has-text('{name}')"
        loc = fr.locator(sel).first
        loc.wait_for(state="visible", timeout=1500)
        loc.scroll_into_view_if_needed(timeout=1000)
        loc.click(timeout=1500, force=True)
        return True
    except Exception:
        pass

    # 3) fallback: role radio atau elemen lain yang berteks
    try:
        loc = fr.get_by_role("radio", name=re.compile(name, re.I)).first
        loc.wait_for(state="visible", timeout=1500)
        loc.click(timeout=1500, force=True)
        return True
    except Exception:
        pass

    try:
        loc = fr.get_by_text(name, exact=False).first
        loc.wait_for(state="visible", timeout=1500)
        loc.click(timeout=1500, force=True)
        return True
    except Exception:
        pass

    return False

def _click_any_frame(page: Page, name: str, template_id: int) -> Frame | None:
    # coba klik di main page dulu
    if _click_in_frame(page.main_frame, name, template_id):
        return page.main_frame
    # lalu di semua frame anak
    for fr in page.frames:
        if fr == page.main_frame:
            continue
        try:
            if _click_in_frame(fr, name, template_id):
                return fr
        except Exception:
            continue
    return None

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
    1) Coba direct API /screener/results (GET/POST) pakai template_id.
    2) Kalau gagal → buka /screener, cari radio/label di SELURUH frames, klik,
       lalu tunggu response /screener/results (wait_for_response).
    """
    # 0) pastikan bearer valid (untuk exodus API)
    _ = get_bearer_token()

    # 1) Direct API (paling stabil, tidak perlu klik UI)
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

    os.makedirs(debug_dir, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(locale="id-ID")
        page = context.new_page()

        page.goto(SCREENER_URL, wait_until="domcontentloaded", timeout=timeout_ms)

        # klik di main frame / child frames
        fr = _click_any_frame(page, name=name, template_id=template_id or -1)
        if not fr:
            if debug:
                page.screenshot(path=os.path.join(debug_dir, "screener_not_found.png"), full_page=True)
            browser.close()
            raise RuntimeError(f"Tidak menemukan template screener dengan teks: {name!r}")

        # tunggu respons /screener/results dari frame yang barusan kita klik
        try:
            res = _wait_results(page, timeout_ms=timeout_ms)
        except Exception:
            # coba tunggu dari frame spesifik
            res = _wait_results(fr, timeout_ms=timeout_ms)

        payload = res["json"]
        out = {
            "_source": "playwright_capture",
            "data": payload,
            "_meta": {
                "status": res["status"],
                "url": res["url"],
                "ts": datetime.now(timezone.utc).isoformat(),
            },
        }

        if debug:
            page.screenshot(path=os.path.join(debug_dir, "screener_ok.png"), full_page=True)

        browser.close()

    return out
