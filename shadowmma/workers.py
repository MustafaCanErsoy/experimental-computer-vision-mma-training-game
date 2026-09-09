"""Managed synthetic/camera workers. Physical capture requires auto_start."""
from time import perf_counter, sleep
from .core import Hit, MOVES
from .event_bridge import EventClient


def synthetic(port=28741, interval=1., stop_file=None):
    client = EventClient("synthetic", port)
    print("SENTETIK DEMO. Kamera kapali. Oyunda P, sonra W.", flush=True)
    index, next_hit = 0, perf_counter() + interval
    try:
        while stop_file is None or not stop_file.exists():
            client.poll(ready=True)
            now = perf_counter()
            if now >= next_hit:
                move = MOVES[index % len(MOVES)]  # Does not read the requested move.
                if client.send_hit(Hit(move, now, now, 0.), now):
                    index += 1
                next_hit = now + interval
            sleep(.01)
    except KeyboardInterrupt:
        pass
    finally:
        client.close()
    return 0


def camera(port=28741, index=0, stop_file=None, *, auto_start=False, report_dir=None, record_frames=False):
    from .app import App
    client = EventClient("camera", port)
    try:
        if stop_file and stop_file.exists():
            return 0
        app = App(index, tower_client=client, auto_start=auto_start, integrated=True,
                  report_dir=report_dir, record_frames=record_frames)

        def check_stop():
            if stop_file and stop_file.exists():
                app.close()
            elif not app.closed:
                app.root.after(100, check_stop)

        app.root.after(100, check_stop)
        app.run()
    finally:
        client.close()
    return 0
