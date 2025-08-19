import os, requests

TG_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")

def send(text: str):
    # Selalu tampilkan ringkasan ke log (agar terlihat di GitHub Actions)
    print("[REPORT]", text[:300].replace("\n", " ") + (" ..." if len(text) > 300 else ""))

    if not (TG_TOKEN and TG_CHAT_ID):
        print("[INFO] Telegram tidak dikonfigurasi; hanya print ke log.")
        return

    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TG_CHAT_ID, "text": text}, timeout=12)
        if r.status_code != 200:
            print("[WARN] Telegram:", r.text)
        else:
            print("[OK] Telegram sent")
    except Exception as e:
        print("[ERR] Telegram gagal:", e)
