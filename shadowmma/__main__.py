import argparse
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="ShadowMMA yerel kamera prototipi")
    parser.add_argument("--camera", type=int, default=0, help="Kamera indeksi (varsayılan: 0)")
    parser.add_argument("--launcher", action="store_true", help="Ortak kaynak secimi ve surec yonetimi")
    parser.add_argument("--reports", action="store_true", help="Son yerel algılama raporunu aç; kamera açılmaz")
    parser.add_argument("--play", choices=("keyboard", "synthetic", "camera"), help="Oyunu ve gereken ureticiyi birlikte baslat")
    parser.add_argument("--worker", choices=("synthetic", "camera"), help=argparse.SUPPRESS)
    parser.add_argument("--stop-file", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--headless", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--smoke-seconds", type=float, help=argparse.SUPPRESS)
    parser.add_argument("--no-camera", action="store_true", help="Kamera kapalı başlangıç kontrolü")
    parser.add_argument("--record-frames", action="store_true", help="Olay çevresindeki seçilmiş kareleri yalnız yerel rapora kaydet")
    parser.add_argument("--auto-camera", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--report-dir", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--check-install", type=Path, metavar="JSON", help="Kamera kapali paket kontrolunu JSON'a yaz")
    parser.add_argument("--tower-demo", action="store_true", help="Kamera acmadan 3D kule demosunu baslat")
    parser.add_argument("--tower-source", choices=("synthetic", "camera"), help="Kuleyi yerel Python olaylarini bekleyerek baslat (kamera acmaz)")
    parser.add_argument("--tower-client", action="store_true", help="Kamera laboratuvarini kuleye bagla; kamera dugmeyle acilir")
    parser.add_argument("--port", type=int, default=28741, help="Yerel olay portu (varsayilan: 28741)")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port 1..65535 araliginda olmali.")
    if sum((args.tower_demo, args.tower_source is not None, args.tower_client, args.launcher,
            args.play is not None, args.worker is not None, args.check_install is not None, args.reports)) > 1:
        parser.error("Tek bir kule modu secin.")
    if args.camera < 0:
        parser.error("Kamera indeksi sifir veya pozitif olmali.")
    if args.smoke_seconds is not None and not .1 <= args.smoke_seconds <= 60:
        parser.error("Kontrol suresi 0.1..60 saniye olmali.")
    if args.check_install:
        from .install_check import check_install
        return check_install(args.check_install)
    if args.reports:
        from .paths import RECOGNITION_REPORTS
        import os
        import webbrowser
        folder = RECOGNITION_REPORTS
        folder.mkdir(parents=True, exist_ok=True)
        reports = sorted(folder.glob("recognition-*/report.html"), key=lambda p: p.stat().st_mtime)
        if reports:
            webbrowser.open(reports[-1].resolve().as_uri())
        else:
            os.startfile(folder)
        return 0
    if args.launcher:
        from .launcher_ui import Launcher
        Launcher().run()
        return 0
    if args.play or (getattr(sys, "frozen", False) and not any((args.worker, args.tower_demo, args.tower_source, args.tower_client))):
        from .tower_launcher import run_session
        return run_session(args.play or "camera", args.port, args.camera, headless=args.headless,
                           seconds=args.smoke_seconds, no_camera=args.no_camera, record_frames=args.record_frames)
    if args.worker:
        from . import workers
        if args.worker == "synthetic":
            return workers.synthetic(args.port, stop_file=args.stop_file)
        return workers.camera(args.port, args.camera, args.stop_file, auto_start=args.auto_camera and not args.no_camera,
                              report_dir=args.report_dir, record_frames=args.record_frames)
    if args.tower_demo:
        from .tower_launcher import launch
        return launch()
    if args.tower_source:
        from .tower_launcher import launch
        return launch(args.tower_source, args.port)
    if args.camera < 0:
        parser.error("Kamera indeksi sifir veya pozitif olmali.")
    try:
        from .app import App
    except ImportError as exc:
        print(f"Baslatilamadi: {exc}. Proje klasorundeki Kurulum.cmd dosyasini calistirin.", file=sys.stderr)
        return 1
    if args.tower_client:
        from .event_bridge import EventClient
        client = EventClient("camera", args.port)
        try:
            App(args.camera, tower_client=client, record_frames=args.record_frames).run()
        finally:
            client.close()
    else:
        App(args.camera, record_frames=args.record_frames).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
