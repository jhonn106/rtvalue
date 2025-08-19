import time
from runners.snap_once import run

if __name__ == "__main__":
    while True:
        try:
            run()
        except Exception as e:
            print("ERROR:", e)
        time.sleep(2)
