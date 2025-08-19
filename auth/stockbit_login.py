import os, json, time, base64
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

TOKEN_PATH = os.environ.get("STOCKBIT_TOKEN_PATH", "token.json")

def _decode_jwt_exp(jwt_token: str):
    try:
        payload_b64 = jwt_token.split(".")[1] + "==="
        payload = json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
        exp = payload.get("exp")
        if exp:
            return datetime.fromtimestamp(int(exp), tz=timezone.utc)
    except Exception:
        pass
    return None

def load_token_if_valid(min_valid_sec=600):
    if not os.path.exists(TOKEN_PATH):
        return None
    try:
        with open(TOKEN_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        token = data.get("access_token")
        exp_iso = data.get("exp_iso")
        if token and exp_iso:
            exp_dt = datetime.fromisoformat(exp_iso)
            if exp_dt - datetime.now(timezone.utc) > timedelta(seconds=min_valid_sec):
                return token
    except Exception:
        pass
    return None

def save_token(token: str):
    exp_dt = _decode_jwt_exp(token) or (datetime.now(timezone.utc) + timedelta(hours=2))
    data = {"access_token": token, "exp_iso": exp_dt.isoformat()}
    with open(TOKEN_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def login_and_capture_token(headless=True, timeout_ms=60000):
    email = os.environ.get("STOCKBIT_EMAIL")
    password = os.environ.get("STOCKBIT_PASSWORD")
    if not email or not password:
        raise RuntimeError("STOCKBIT_EMAIL & STOCKBIT_PASSWORD wajib diisi (Secrets/ENV).")

    captured = {"token": None}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()

        def on_request(req):
            try:
                url = req.url
                if "exodus.stockbit.com" in url:
                    auth = req.headers.get("authorization") or req.headers.get("Authorization")
                    if auth and auth.lower().startswith("bearer "):
                        captured["token"] = auth.split(" ", 1)[1].strip()
            except Exception:
                pass

        page.on("request", on_request)

        page.goto("https://stockbit.com/login", timeout=timeout_ms)

        # Isi form login (fallback multi-selector)
        try:
            page.get_by_placeholder("Email").fill(email)
        except Exception:
            page.locator("input[type='email'], input[name*='email']").first.fill(email)

        try:
            page.get_by_placeholder("Password").fill(password)
        except Exception:
            page.locator("input[type='password']").first.fill(password)

        # Klik tombol
        try:
            page.get_by_role("button", name=lambda n: "log" in n.lower() or "masuk" in n.lower()).click()
        except Exception:
            page.locator("button:has-text('Log'), button:has-text('Masuk')").first.click()

        page.wait_for_load_state("networkidle", timeout=timeout_ms)

        page.goto("https://stockbit.com/stream", timeout=timeout_ms)

        t0 = time.time()
        while not captured["token"] and time.time() - t0 < 30:
            page.wait_for_timeout(500)

        browser.close()

    if not captured["token"]:
        raise RuntimeError("Gagal menangkap Bearer token dari request exodus.")
    save_token(captured["token"])
    return captured["token"]

def get_bearer_token():
    token = load_token_if_valid()
    if token:
        return token
    return login_and_capture_token(headless=True)
