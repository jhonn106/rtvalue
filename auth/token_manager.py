import os, json
from datetime import datetime, timedelta, timezone

from auth.stockbit_login import get_bearer_token  # sudah ada di project

TOKEN_PATH = os.environ.get("STOCKBIT_TOKEN_PATH", "token.json")

class TokenManager:
    def __init__(self):
        self._token = None
        self._exp = None  # datetime (UTC)

        # coba load dari env terlebih dulu
        env_tok = os.environ.get("STOCKBIT_BEARER")
        env_exp = os.environ.get("STOCKBIT_BEARER_EXP")  # ISO8601 optional
        if env_tok:
            self._token = env_tok.strip()
            if env_exp:
                try:
                    self._exp = datetime.fromisoformat(env_exp.replace("Z","+00:00"))
                except Exception:
                    self._exp = None

        # kalau belum ada exp/env, coba baca dari token.json
        if not self._exp or not self._token:
            self._load_file()

    def _load_file(self):
        try:
            with open(TOKEN_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            tok = data.get("token") or data.get("bearer") or data.get("access_token")
            exp = data.get("exp") or data.get("expires_at")
            if tok:
                self._token = tok
            if exp:
                try:
                    self._exp = datetime.fromisoformat(str(exp).replace("Z","+00:00"))
                except Exception:
                    self._exp = None
        except Exception:
            pass

    def _save_file(self):
        try:
            with open(TOKEN_PATH, "w", encoding="utf-8") as f:
                json.dump({
                    "token": self._token,
                    "exp": self._exp.astimezone(timezone.utc).isoformat() if self._exp else None
                }, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _about_to_expire(self, margin_minutes=5):
        if not self._exp:
            return False  # nggak tahu → treat as valid sampai 401
        now = datetime.now(timezone.utc)
        return now >= (self._exp - timedelta(minutes=margin_minutes))

    def refresh(self):
        """
        Force refresh via Playwright login. stockbit_login.get_bearer_token()
        sudah menangkap dan menyimpan token + exp ke token.json.
        """
        tok = get_bearer_token()  # ini juga akan menulis token.json + exp
        self._token = tok
        # muat ulang exp dari file (get_bearer_token mencetak exp)
        self._load_file()
        self._save_file()
        return self._token

    def get_token(self):
        # kalau punya exp & mau expired, refresh
        if self._about_to_expire():
            try:
                self.refresh()
            except Exception:
                # kalau gagal refresh, tetap balikin token lama; request nanti akan 401 dan kita retry di layer klien
                pass
        if not self._token:
            # tidak punya token sama sekali → refresh
            self.refresh()
        return self._token

# singleton
manager = TokenManager()
