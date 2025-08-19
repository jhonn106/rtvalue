import time
from runners.snap_once import run

if __name__ == "__main__":
    start = time.time()
    i = 0
    # Loop ±20 menit (1200 detik) sesuai limit Actions
    while time.time() - start < 1200:
        i += 1
        print(f"[LOOP] iter={i}")
        try:
            run()
        except Exception as e:
            print("[ERR]", e)
        time.sleep(5)
    print("[DONE] loop selesai")
