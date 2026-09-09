"""Optional developer source picker; the normal entry opens the camera game."""
import tkinter as tk
from tkinter import ttk
from .tower_launcher import Session


class Launcher:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("ShadowMMA · Karanlık Kule")
        self.root.geometry("600x440")
        self.root.minsize(560, 420)
        self.session = Session()
        self.source = tk.StringVar(value="camera")
        self.port = tk.StringVar(value="28741")
        self.camera = tk.StringVar(value="0")
        self.status = tk.StringVar(value="Bir kaynak seç ve kuleye gir.")
        frame = ttk.Frame(self.root, padding=24)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="KARANLIK KULE", font=("Segoe UI", 22, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Üç kat · Kül Muhafızı · Yerel ilerleme").pack(anchor="w", pady=(0, 16))
        for value, label in (("keyboard", "Klavye demosu — kamera kapalı"),
                             ("synthetic", "Sentetik demo — Python vuruşları, kamera kapalı"),
                             ("camera", "Kamera oyunu — kamera ve hazırlık otomatik")):
            ttk.Radiobutton(frame, text=label, variable=self.source, value=value).pack(anchor="w", pady=3)
        ttk.Label(frame, text="Kamera ile hareket doğruluğu henüz insanla doğrulanmadı.").pack(anchor="w", pady=(8, 12))
        options = ttk.Frame(frame)
        options.pack(fill="x")
        ttk.Label(options, text="Yerel port").pack(side="left")
        ttk.Entry(options, textvariable=self.port, width=8).pack(side="left", padx=(8, 20))
        ttk.Label(options, text="Kamera indeksi").pack(side="left")
        ttk.Entry(options, textvariable=self.camera, width=5).pack(side="left", padx=8)
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=16)
        self.start_button = ttk.Button(buttons, text="Kuleye gir", command=self.start)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(buttons, text="Seansı kapat", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=10)
        ttk.Label(frame, textvariable=self.status, wraplength=510).pack(anchor="w")
        ttk.Label(frame, text="Kamera: ellerin görünürken otomatik başlar. Sentetik: P, ardından W.").pack(anchor="w", pady=8)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Escape>", lambda _: self.close())
        self.poll_id = self.root.after(150, self.poll)

    def start(self):
        try:
            self.session.start(self.source.get(), int(self.port.get()), int(self.camera.get()))
        except (ValueError, OSError, RuntimeError) as exc:
            self.status.set(f"Başlatılamadı: {exc}")
            return
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status.set("Seans açık. Oyunu, laboratuvarı veya bu pencereyi kapatmak bağlı süreçleri kapatır.")

    def stop(self, message="Seans kapatıldı. Yeni kaynakla tekrar başlayabilirsin."):
        self.session.close()
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.status.set(message)

    def poll(self):
        ended = self.session.poll()
        if ended is not None:
            index, code = ended
            message = "Seans kapatıldı."
            if code:
                message = f"{'Oyun' if index == 0 else 'Üretici'} hata ile kapandı ({code}). Kayıt: {self.session.log_path}"
            self.stop(message)
        self.poll_id = self.root.after(150, self.poll)

    def close(self):
        self.root.after_cancel(self.poll_id)
        self.session.close()
        self.root.destroy()

    def run(self):
        try:
            self.root.mainloop()
        finally:
            self.session.close()
