"""
Runner: Refresh Stockbit Token
Dipakai untuk memperbarui token (bearer) secara otomatis.
"""

import json
from pathlib import Path
from auth.stockbit_login import login_and_capture_token

TOKEN_PATH = Path("token.json")

def main():
    print("[REFRESH] Memulai proses refresh token...")

    # Login ulang ke Stockbit → dapatkan bearer token baru
    try:
        new_tok = login_and_capture_token(headless=True)
    except Exception as e:
        print(f"[REFRESH ERROR] Gagal login: {e}")
        return

    if not new_tok or "token" not in new_tok:
        print("[REFRESH ERROR] Tidak ada token baru yang didapat.")
        return

    # Simpan ke file token.json
    try:
        TOKEN_PATH.write_text(json.dumps(new_tok, indent=2))
        print(f"[REFRESH] Token baru berhasil disimpan ke {TOKEN_PATH}")
        print(f"[REFRESH] Expired at: {new_tok.get('exp')}")
    except Exception as e
