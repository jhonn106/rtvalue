# auth/stockbit_login.py (tambahkan util & perbarui get_bearer_token)

import os, json, time, base64, threading
from pathlib import Path
from typing import Optional

TOKEN_PATH = Path(os.environ.get("STOCKBIT_TOKEN_PATH", "token.json"))

# ini harus sudah ada di file kamu:
# def login_and_capture_token(headless: bool = True) -> str: ...
# yang mengembalikan string bearer terbaru dan menyimpan ke token.json

_LOCK = threading.Lock()

def _decode_jwt_exp(bearer: str) -> Optional[int]:
    """
    Kembalikan exp (epoch seconds) dari JWT kalau ada, else None.
    """
    try:
        parts = bearer.split(".")
        if len(parts) < 2:
            return None
        payload_b64 = parts[1] + "==="  # pad
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return int(payload.get("exp")) if "exp" in payload else None
    except Exception:
        return None

def _read_tokenfile() -> Optional[str]:
    try:
        if TOKEN_PATH.exists():
            data = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
            tok = data.get("token") or data.get("bearer") or data.get("access_token")
            if tok:
                return tok
    except Exception:
        pass
    return None

def _write_tokenfile(bearer: str, exp: Optional[int] = None):
    payload = {"token": bearer}
    if exp:
        payload["exp"] = exp
    TOKEN_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

def get_bearer_token(headless: bool = True, min_remaining_sec: int = 600) -> str:
    """
    Ambil bearer yang valid.
    - Prioritas: token.json
    - Jika tidak ada, coba dari env STOCKBIT_BEARER (hanya bootstrap)
    - Cek sisa umur JWT (exp). Jika < min_remaining_sec → refresh
    - Kalau request nanti 401/403, klien akan panggil login_and_capture_token() lagi.
    """
    with _LOCK:
        # 1) dari token.json
        tok = _read_tokenfile()

        # 2) kalau belum ada, bootstrap dari ENV sekali
        if not tok:
            tok = os.environ.get("STOCKBIT_BEARER")

        def _should_refresh(token: Optional[str]) -> bool:
            if not token:
                return True
            exp = _decode_jwt_exp(token)
            if not exp:
                # kalau tidak bisa dibaca exp, aman: refresh saja
                return True
            now = int(time.time())
            return (exp - now) <= min_remaining_sec

        # 3) refresh kalau perlu
        if _should_refresh(tok):
            new_tok = login_and_capture_token(headless=headless)
            exp = _decode_jwt_exp(new_tok)
            _write_tokenfile(new_tok, exp)
            return new_tok

        # 4) token cukup panjang umurnya → simpan lagi (agar format konsisten)
        exp = _decode_jwt_exp(tok)
        _write_tokenfile(tok, exp)
        return tok
