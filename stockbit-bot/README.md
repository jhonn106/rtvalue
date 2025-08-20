# stockbit-bot

Bot snapshot **Top Gainer**, **Top Value**, **Running Trade**, dan **PowerBuy** dari Stockbit.
Menyertakan **auto-login** (Playwright) untuk ambil **Bearer token** otomatis, dan **GitHub Actions** untuk menjalankan snapshot terjadwal.

> **Catatan**: Gunakan dengan bijak dan sesuai ToS platform terkait. Token akun Anda bersifat rahasia.

## Struktur
```
stockbit-bot/
├─ README.md
├─ requirements.txt
├─ .env.example
├─ config.yaml
├─ auth/
│  └─ stockbit_login.py
├─ clients/
│  ├─ token_store.py
│  └─ stockbit.py
├─ logic/
│  ├─ rolling.py
│  └─ rules.py
├─ notif/
│  └─ telegram.py
├─ runners/
│  ├─ snap_once.py
│  └─ live_loop.py
└─ .github/
   └─ workflows/
      └─ stockbit.yml
```

## Menjalankan Lokal
1. Buat virtualenv & install deps
   ```bash
   pip install -r requirements.txt
   ```
2. Salin `.env.example` menjadi `.env` dan isi `STOCKBIT_EMAIL`, `STOCKBIT_PASSWORD` (opsional TG).
3. Jalankan snapshot sekali:
   ```bash
   python -m runners.snap_once
   ```
4. Mode loop (untuk VPS, bukan Actions):
   ```bash
   python -m runners.live_loop
   ```

## GitHub Actions
- Tambahkan **Secrets** pada repo:
  - `STOCKBIT_EMAIL`, `STOCKBIT_PASSWORD`
  - (opsional) `TG_TOKEN`, `TG_CHAT_ID`
- Workflow `stockbit.yml` akan auto-login lalu menjalankan snapshot.
