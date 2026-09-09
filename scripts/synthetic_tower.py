"""Camera-free input producer; cycles observed classes independently of prompts."""
import argparse
from pathlib import Path
import sys
from time import perf_counter, sleep

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shadowmma.core import Hit, MOVES
from shadowmma.event_bridge import EventClient


def main():
    parser = argparse.ArgumentParser(description="Kamera kapali, sentetik Python -> Godot olaylari")
    parser.add_argument("--port", type=int, default=28741)
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or not .3 <= args.interval <= 60:
        parser.error("Port 1..65535; aralik 0.3..60 saniye olmali.")
    client = EventClient("synthetic", args.port)
    print("SENTETIK DEMO. Kamera acilmaz. Oyunda P, sonra W. Durdur: Ctrl+C.", flush=True)
    index, next_hit, previous = 0, perf_counter() + args.interval, None
    try:
        while True:
            client.poll(ready=True)
            if client.status != previous:
                previous = client.status
                print(previous, flush=True)
            now = perf_counter()
            if now >= next_hit:
                # Never read the requested move to manufacture detection accuracy.
                move = MOVES[index % len(MOVES)]
                if client.send_hit(Hit(move, now, now, 0.), now):
                    print("Sentetik olay:", move, flush=True)
                    index += 1
                next_hit = now + args.interval
            sleep(.01)
    except KeyboardInterrupt:
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
