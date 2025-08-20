# auth/stockbit_login.py
import os
import re
import json
import base64
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

STOCKBIT_EMAIL = os.environ.get("STOCKBIT_EMAIL")
STOCKBIT_PASSWORD = os.environ.get("STOCKBIT_PASSWORD")
TOKEN_PATH = os.environ.get("STOCKBIT_TOKEN_PATH", "token.json")

STREAM_URL = "https://stockbit.com/#/stream"  # memicu panggilan ke exodus
EXODUS_HOST = "exodus.stockbit.com"

# -------- helpers --------

def _b64url_decode(data: str) -> bytes:
    padding = '=' * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)

def _parse_jwt_exp(tok: str):
    """Coba baca exp dari JWT; kalau bukan JWT, return None."""
    try:
        parts = tok.split(".")
        if len(parts) != 3:
            return None
        payload = json.loads(_b64url_decode(parts[1]).decode("utf-8"))
        exp = payload.get("exp")
        if isinstance(exp, (int, float)):
            return datetime.fromtimestamp(exp, tz=timezone.utc)
    except Exception:
        return None
    return None

def _save_token(token: str, exp_dt: datetime | None):
    data = {
        "token": token,
        "exp": exp_dt.astimezone(timezone.utc).isoformat() if exp_dt else None,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    Path(TOKEN_PATH).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[AUTH] Token saved, exp: {data['exp']}")

def _load_token():
    try:
        data = json.loads(Path(TOKEN_PATH).read_text(encoding="utf-8"))
        tok = data.get("token")
        exp = data.get("exp")
        exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00")) if exp else None
        return tok, exp_dt
    except Exception:
        return None, None

def _token_still_valid(exp_dt: datetime | None, margin_minutes=5) -> bool:
    if not exp_dt:
        return False
    now = datetime.now(timezone.utc)
    return now < (exp_dt - timedelta(minutes=margin_minutes))

def _guess_exp(token: str) -> datetime | None:
    # coba baca dari JWT, jika gagal beri default 10 jam
    exp_dt = _parse_jwt_exp(token)
    if exp_dt:
        return exp_dt
    return datetime.now(timezone.utc) + timedelta(hours=10)

# -------- core login & capture --------

def login_and_capture_token(headless: bool = True, timeout_sec: int = 90) -> str:
    """
    Login via Playwright → tangkap Authorization: Bearer ... dari request ke exodus.
    Simpan ke TOKEN_PATH bersama 'exp' (dari JWT atau fallback +10 jam).
    """
    assert STOCKBIT_EMAIL and STOCKBIT_PASSWORD, "Set STOCKBIT_EMAIL & STOCKBIT_PASSWORD terlebih dahulu."

    bearer_holder = {"token": None}

    def _on_request(req):
        try:
            url = req.url or ""
            if EXODUS_HOST in url:
                # cari header authorization
                auth = None
                for k, v in req.headers.items():
                    if k.lower() == "authorization" and v:
                        auth = v
                        break
                if auth:
                    m = re.search(r"Bearer\s+(.+)", auth, flags=re.I)
                    if m:
                        bearer_holder["token"] = m.group(1).strip()
        except Exception:
            pass

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(locale="id-ID")
        page = context.new_page()

        context.on("request", _on_request)

        print("[AUTH] Opening login page…")
        page.goto("https://stockbit.com/#/login", wait_until="domcontentloaded", timeout=timeout_sec * 1000)

        # form klasik
        try:
            page.fill('input[name="username"], input[name="email"]', STOCKBIT_EMAIL, timeout=15_000)
        except Exception:
            # beberapa layout pakai selector berbeda
            page.fill('input[type="email"]', STOCKBIT_EMAIL, timeout=15_000)

        try:
            page.fill('input[name="password"]', STOCKBIT_PASSWORD, timeout=15_000)
        except Exception:
            page.fill('input[type="password"]', STOCKBIT_PASSWORD, timeout=15_000)

        # klik tombol login
        selectors = [
            'button:has-text("Login")',
            'button:has-text("Masuk")',
            'button[type="submit"]',
        ]
        clicked = False
        for sel in selectors:
            try:
                page.click(sel, timeout=3_000)
                clicked = True
                break
            except Exception:
                continue
        if not clicked:
            raise RuntimeError("Tidak menemukan tombol Login.")

        # tunggu redirect / halaman stream
        page.wait_for_timeout(1500)
        print("[AUTH] Navigating to stream to trigger exodus calls…")
        page.goto(STREAM_URL, wait_until="domcontentloaded", timeout=timeout_sec * 1000)

        # picu beberapa aksi supaya request exodus muncul
        for _ in range(6):
            if bearer_holder["token"]:
                break
            # reload ringan
            page.reload(wait_until="networkidle", timeout=timeout_sec * 1000)
            page.wait_for_timeout(1500)

        # fallback: coba baca dari localStorage/cookies
        if not bearer_holder["token"]:
            try:
                # beberapa aplikasi menyimpan akses token di localStorage
                ls = page.evaluate("() => Object.assign({}, window.localStorage)")
                if isinstance(ls, dict):
                    for k, v in ls.items():
                        if not isinstance(v, str):
                            continue
                        if re.search(r"eyJ", v) and len(v) > 100:  # heuristik JWT
                            bearer_holder["token"] = v
                            break
            except Exception:
                pass

        # last chance: sniff response headers (jika ada endpoint auth)
        # (sudah cukup jarang diperlukan; request hook di atas biasanya cukup)

        # pastikan token ketemu
        token = bearer_holder["token"]
        if not token:
            # sebagai alternatif, beberapa halaman SPA butuh delay sedikit lebih lama
            page.wait_for_timeout(2000)
            token = bearer_holder["token"]

        browser.close()

    if not token:
        raise RuntimeError("Gagal menangkap bearer dari request exodus atau localStorage/cookies.")

    exp_dt = _guess_exp(token)
    _save_token(token, exp_dt)
    return token

# -------- public API --------

def get_bearer_token() -> str:
    """
    Ambil bearer siap pakai:
      1) Jika token.json ada & belum mau kadaluarsa (margin 5 menit) → pakai itu
      2) Jika env STOCKBIT_BEARER ada, dan kita tidak punya token.json valid → pakai env (simpan ke file + exp)
      3) Jika tidak valid → login Playwright dan simpan baru
    """
    # 1) file token
    tok, exp_dt = _load_token()
    if tok and _token_still_valid(exp_dt, margin_minutes=5):
        print("[AUTH] Using bearer from token.json.")
        return tok

    # 2) env bearer
    env_tok = os.environ.get("STOCKBIT_BEARER")
    if env_tok:
        print("[AUTH] Using STOCKBIT_BEARER from env.")
        exp_dt = _guess_exp(env_tok)
        _save_token(env_tok, exp_dt)
        return env_tok

    # 3) login
    return login_and_capture_token(headless=True)
