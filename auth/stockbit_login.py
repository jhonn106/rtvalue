import os, json, time, base64, re
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

TOKEN_PATH = os.environ.get("STOCKBIT_TOKEN_PATH", "token.json")

JWT_RE = re.compile(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$")

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
    print("[AUTH] Token saved, exp:", exp_dt.isoformat())

def _try_extract_jwt_from_local_storage(page):
    """Cari token di localStorage—banyak SPA menyimpan accessToken di sana."""
    try:
        keys = page.evaluate("Object.keys(window.localStorage)")
        for k in keys:
            v = page.evaluate(f"window.localStorage.getItem({json.dumps(k)})")
            # jika value JSON, parse
            try:
                j = json.loads(v)
                # cari kandidat field token
                for cand in ["access_token", "accessToken", "token", "idToken", "jwt"]:
                    if isinstance(j, dict) and j.get(cand) and isinstance(j[cand], str):
                        t = j[cand]
                        if JWT_RE.match(t):
                            print(f"[AUTH] Found JWT in localStorage key={k} field={cand}")
                            return t
            except Exception:
                # kalau bukan JSON, cek langsung string
                if isinstance(v, str) and JWT_RE.match(v):
                    print(f"[AUTH] Found JWT string in localStorage key={k}")
                    return v
        return None
    except Exception as e:
        print("[AUTH] localStorage scan error:", e)
        return None

def _try_extract_jwt_from_cookies(context):
    try:
        for c in context.cookies():
            # kadang nama cookie mengandung token
            if c.get("name") and "token" in c["name"].lower():
                val = c.get("value", "")
                if JWT_RE.match(val):
                    print(f"[AUTH] Found JWT in cookie name={c['name']}")
                    return val
        return None
    except Exception as e:
        print("[AUTH] cookie scan error:", e)
        return None

def login_and_capture_token(headless=True, timeout_ms=90000):
    email = os.environ.get("STOCKBIT_EMAIL")
    password = os.environ.get("STOCKBIT_PASSWORD")
    if not email or not password:
        raise RuntimeError("STOCKBIT_EMAIL & STOCKBIT_PASSWORD wajib diisi (Secrets/ENV).")

    captured = {"token": None}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()

        # strategy A: tangkap dari request header
        def on_request(req):
            try:
                if "exodus.stockbit.com" in req.url:
                    auth = req.headers.get("authorization") or req.headers.get("Authorization")
                    if auth and auth.lower().startswith("bearer "):
                        captured["token"] = auth.split(" ", 1)[1].strip()
                        print("[AUTH] Captured Bearer from exodus request")
            except Exception:
                pass

        page.on("request", on_request)

        # 1) Buka login
        print("[AUTH] Opening login page…")
        page.goto("https://stockbit.com/login", timeout=timeout_ms)

        # 2) Isi form login (multi selector)
        try:
            page.get_by_placeholder("Email").fill(email)
        except Exception:
            page.locator("input[type='email'], input[name*='email']").first.fill(email)

        try:
            page.get_by_placeholder("Password").fill(password)
        except Exception:
            page.locator("input[type='password']").first.fill(password)

        # Klik tombol login
        try:
            page.get_by_role("button", name=lambda n: "log" in n.lower() or "masuk" in n.lower()).click()
        except Exception:
            page.locator("button:has-text('Log'), button:has-text('Masuk')").first.click()

        page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        page.wait_for_load_state("networkidle", timeout=timeout_ms)

        # 3) Strategy B: coba baca token dari localStorage/cookies setelah login
        token = _try_extract_jwt_from_local_storage(page)
        if not token:
            token = _try_extract_jwt_from_cookies(context)

        # 4) Strategy C: paksa halaman yang memicu panggilan exodus
        print("[AUTH] Navigating to stream to trigger exodus calls…")
        page.goto("https://stockbit.com/stream", timeout=timeout_ms)
        page.wait_for_load_state("networkidle", timeout=timeout_ms)

        # tunggu event request jika belum dapat token
        t0 = time.time()
        while not (captured["token"] or token) and time.time() - t0 < 35:
            page.wait_for_timeout(500)
            # ulangi cek localStorage
            if not token:
                token = _try_extract_jwt_from_local_storage(page)

        browser.close()

    final_token = captured["token"] or token
    if not final_token:
        raise RuntimeError("Gagal menangkap Bearer token dari request exodus atau localStorage/cookies.")

    save_token(final_token)
    return final_token
def get_bearer_token():
    # 1) Prioritas ENV: STOCKBIT_BEARER (secret)
    env_tok = os.environ.get("STOCKBIT_BEARER")
    if env_tok:
        try:
            save_token(env_tok.strip())
            print("[AUTH] Using STOCKBIT_BEARER from env.")
            return env_tok.strip()
        except Exception:
            pass

    # 2) Pakai token file jika masih valid
    token = load_token_if_valid()
    if token:
        print("[AUTH] Using cached token.json")
        return token

    # 3) Terakhir: coba login Playwright (kadang diblok headless di CI)
    print("[AUTH] Falling back to Playwright login…")
    return login_and_capture_token(headless=True)

