import os, requests

TG_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")

def send(text: str):
    if not (TG_TOKEN and TG_CHAT_ID):
        print(text)
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": TG_CHAT_ID, "text": text}, timeout=12)
    if r.status_code != 200:
        print("[WARN] Telegram:", r.text)
