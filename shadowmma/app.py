"""Small Turkish desktop lab. No levels, server, paid API or frame persistence."""
from collections import deque
from time import perf_counter
from math import isfinite
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from PIL import Image, ImageTk
from . import __version__
from .core import Calibration, Detector, Features, MOVES, LABELS, extract
from .metrics import Trial, save_report, summarize
from .vision import Camera, Pose, preview
from .paths import DATA as ROOT
from .paths import RECOGNITION_REPORTS
from .diagnostics import RecognitionReport, session_folder

BG, PANEL, TEXT, MUTED, ACCENT = "#101723", "#1b2736", "#e7eff7", "#a5b5c7", "#89e3b0"


class App:
    def __init__(self, camera_index=0, tower_client=None, *, auto_start=False, integrated=False,
                 report_dir=None, record_frames=False):
        self.root = tk.Tk()
        if integrated:
            self.root.withdraw()
        self.auto_start, self.integrated = auto_start, integrated
        self.retry_at = 0.
        self.report = RecognitionReport(report_dir, record_frames=record_frames, async_writes=True) if report_dir else None
        self.record_frames = record_frames
        self.report_status = ""
        self.last_sample_report = 0.
        self.last_tracking_evidence = -10.
        self.attempt = 0
        self.active_attempt = False
        self.event_attempts = {}
        self.last_attempt_checks = {}
        self.last_attempt_measures = {}
        self.delivery_status = ""
        self.root.title(f"ShadowMMA · Kamera laboratuvarı {__version__}")
        self.root.configure(bg=BG)
        self.root.minsize(1060, 760)
        self.camera_index = camera_index
        self.tower_client = tower_client
        self.tower_status = tk.StringVar(value="Kule bağlantısı bekleniyor" if tower_client else "")
        self.camera = self.pose = None
        self.last_sequence = -1
        self.last_frame_time = 0.
        self.features = None
        self.calibration = None
        self.detector = None
        self.trials = []
        self.current = None
        self.queue = deque()
        self.phase = "idle"
        self.deadline = 0.
        self.last_trial_sample = None
        self.invalid_since = None
        self.software_ms, self.inference_ms, self.event_ms = (deque(maxlen=10000) for _ in range(3))
        self.frame_times = deque(maxlen=60)
        self.closed = False
        self.optical_ms = None
        self.requested = tk.StringVar(value="Sol yumruk")
        self.status = tk.StringVar(value="Kamera kapalı. Kamerayı aç ile başla.")
        self.last_detection = tk.StringVar(value="")
        self.prompt = tk.StringVar(value="Önce kadraja yerleş ve kalibre et.")
        self.feedback = tk.StringVar(value="Deneysel algılayıcı · insanla henüz doğrulanmadı")
        self.timings = tk.StringVar(value="Gecikme ölçümü bekleniyor.")
        self.stats = tk.StringVar(value="Etiketli test yapılmadı; doğruluk henüz bilinmiyor.")
        self.test_info = tk.StringVar(value="14 deneme · her denemeden sonra yaptığını onayla.")
        self.progress = tk.DoubleVar(value=0.)
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Escape>", lambda _: self.close())
        self.root.after(20, self.tick)
        if auto_start:
            self.root.after(1, self.start_automatic)

    def _label(self, parent, text=None, var=None, size=11, color=TEXT, wrap=360):
        label = tk.Label(parent, text=text, textvariable=var, bg=parent["bg"], fg=color,
                         font=("Segoe UI", size), wraplength=wrap, justify="left", anchor="w")
        label.pack(fill="x", pady=5)
        return label

    def _build(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TButton", font=("Segoe UI", 10), padding=7)
        header = tk.Frame(self.root, bg=BG, padx=18, pady=10)
        header.pack(fill="x")
        self._label(header, "SHADOWMMA  /  TEKNİK PROTOTİP", size=19, wrap=1000)
        self._label(header, "Tek oyuncu • Yerel görüntü işleme • Ses kaydı yok • Olay görselleri isteğe bağlı", color=MUTED, wrap=1000)
        body = tk.Frame(self.root, bg=BG, padx=18)
        body.pack(fill="both", expand=True)
        left = tk.Frame(body, bg=BG)
        left.pack(side="left", fill="both", expand=True, anchor="n")
        self.video = tk.Label(left, bg="#080d14", fg=MUTED, text="Kamera önizlemesi", width=80, height=28)
        self.video.pack(anchor="n")
        self._label(left, var=self.status, color=ACCENT, wrap=640)
        self._label(left, var=self.last_detection, color=MUTED, wrap=640)
        if self.tower_client:
            self._label(left, var=self.tower_status, color=ACCENT, wrap=640)
        self._label(left, var=self.timings, color=MUTED, size=10, wrap=640)
        self._label(left, "Omuzların ve iki elin görünür olsun. Kameraya yaklaşık önden bak; tek kişi ve iyi ışık kullan.", color=MUTED, size=10, wrap=640)
        right = tk.Frame(body, bg=PANEL, padx=16, pady=10, width=360)
        right.pack(side="right", fill="both", padx=(16, 0))
        self.camera_button = ttk.Button(right, text="Kamerayı aç", command=self.toggle_camera)
        self.camera_button.pack(fill="x", pady=4)
        ttk.Button(right, text="Yeniden hazırla", command=self.calibrate).pack(fill="x", pady=8)
        ttk.Progressbar(right, variable=self.progress, maximum=1.).pack(fill="x")
        self._label(right, "Serbest deneme: istenen hareket")
        self.move_box = ttk.Combobox(right, textvariable=self.requested, state="readonly", values=[LABELS[m] for m in MOVES])
        self.move_box.pack(fill="x")
        self.move_box.bind("<<ComboboxSelected>>", self.move_changed)
        if self.tower_client:
            self.move_box.configure(state="disabled")
            self.prompt.set("Hareket isteği kule ekranında gösterilir.")
        self._label(right, var=self.prompt, size=16, color=ACCENT)
        self._label(right, var=self.feedback, size=11)
        ttk.Separator(right).pack(fill="x", pady=8)
        ttk.Button(right, text="Etiketli testi başlat / yeniden başlat", command=self.start_test,
                   state="disabled" if self.tower_client else "normal").pack(fill="x")
        self._label(right, var=self.test_info, size=10, color=MUTED)
        row = tk.Frame(right, bg=PANEL)
        row.pack(fill="x")
        self.yes = ttk.Button(row, text="İsteneni yaptım", command=lambda: self.confirm(True), state="disabled")
        self.yes.pack(side="left", expand=True, fill="x")
        self.no = ttk.Button(row, text="Atla / yapmadım", command=lambda: self.confirm(False), state="disabled")
        self.no.pack(side="left", expand=True, fill="x", padx=(4, 0))
        self._label(right, var=self.stats, size=10)
        ttk.Button(right, text="Sayısal raporu kaydet", command=self.save).pack(fill="x", pady=8)
        ttk.Button(right, text="Algılama raporunu aç", command=self.open_report).pack(fill="x")
        ttk.Button(right, text="Harici gecikme ölçümü ekle (isteğe bağlı)", command=self.add_optical).pack(fill="x")
        footer = tk.Frame(self.root, bg=BG, padx=18, pady=8)
        footer.pack(fill="x")
        self._label(footer, "Bu araç profesyonel antrenör değildir; güç, kusursuz teknik veya sakatlanma önleme ölçmez. Rahat tempoda, çevrende boş alanla dene. Esc: çıkış.", size=10, color=MUTED, wrap=1050)

    def toggle_camera(self):
        if self.camera:
            self.stop_camera()
            self.status.set("Kamera kapalı.")
            return
        try:
            self.ensure_report()
            self.report.add("camera", "Kamera ve model hazırlanıyor", detail=f"Kamera indeksi: {self.camera_index}")
            self.status.set("Yerel model yükleniyor…")
            self.root.update_idletasks()
            self.pose = Pose()
            self.camera = Camera(self.camera_index)
            self.last_sequence = -1
            self.last_frame_time = 0.
            self.frame_times.clear()
            self.camera_opened_at = perf_counter()
            self.camera_button.configure(text="Kamerayı kapat")
            self.status.set("Kamera açılıyor…")
            self.calibrate()
        except Exception as exc:
            self.stop_camera()
            self.status.set("Kamera/model açılamadı: " + str(exc))
            if self.report:
                self.report.add("camera", self.status.get())
            self.retry_at = perf_counter()+5.
            if not self.integrated:
                messagebox.showerror("Başlatılamadı", str(exc))

    def ensure_report(self):
        if self.report is None:
            self.report = RecognitionReport(session_folder(RECOGNITION_REPORTS), record_frames=self.record_frames, async_writes=True)

    def start_automatic(self):
        if not self.closed and self.camera is None:
            self.retry_at = perf_counter()+5.
            self.toggle_camera()

    def open_report(self):
        import webbrowser
        self.ensure_report()
        self.report.flush(force=True)
        if self.report.path.is_file():
            webbrowser.open(self.report.path.resolve().as_uri())
        else:
            self.status.set(self.report.error)

    def stop_camera(self, reason="camera_closed"):
        self.cancel_test(reason)
        if self.report and self.active_attempt:
            self.report.add("rejected", "Deneme tamamlanmadan kamera/işleme durdu", detail=reason,
                            attempt=self.attempt, evidence=True)
            self.active_attempt = False
        self.last_detection.set("")
        self.detector = self.calibration = self.features = None
        self.sync_tower()
        if self.camera:
            self.camera.close()
            self.camera = None
        if self.pose:
            self.pose.close()
            self.pose = None
        self.progress.set(0.)
        self.camera_button.configure(text="Kamerayı aç")
        self.video.configure(image="", text="Kamera kapalı", width=80, height=28)
        self.video.image = None
        self.sync_tower()

    def move_changed(self, _=None):
        if self.phase == "idle":
            if self.detector:
                self.detector.reset("Hedef değişti; ellerini kısa bir an sabit tut.")
            self.prompt.set(self.requested.get())

    def calibrate(self):
        if not self.camera:
            self.status.set("Önce kamerayı aç.")
            return
        self.cancel_test("recalibrated")
        if self.report and self.active_attempt:
            self.report.add("rejected", "Yeniden hazırlık nedeniyle deneme tamamlanmadı", attempt=self.attempt, evidence=True)
        self.last_detection.set("")
        self.calibration = Calibration()
        self.detector = None
        self.sync_tower()
        self.progress.set(0.)
        self.prompt.set("Ellerin görünsün; kısa bir an rahatça sabit dur.")
        self.feedback.set("Gard veya duruş seçimi gerekmez. Omuzların ve ellerin kadrajda olsun.")
        self.active_attempt = False
        if self.report:
            self.report.add("calibration", "Otomatik hazırlık başladı", detail="neutral")

    def cancel_test(self, reason=None):
        if reason and self.current is not None and self.phase in ("active", "confirm"):
            self.current.aborted_reason = reason
            self.trials.append(self.current)
            self.refresh_stats()
            self.test_info.set("Kesilen deneme raporda ayrı tutuldu; doğruluk hesabına katılmadı.")
        self.phase = "idle"
        self.current = None
        self.queue.clear()
        self.yes.configure(state="disabled")
        self.no.configure(state="disabled")
        self.move_box.configure(state="disabled" if self.tower_client else "readonly")

    def start_test(self):
        if self.tower_client:
            self.status.set("Kule bağlantısı açıkken etiketli test kullanılmaz; ayrı laboratuvarı aç.")
            return
        if not self.detector:
            self.status.set("Test için önce kalibrasyonu tamamla.")
            return
        self.cancel_test("test_restarted")
        # Fixed order gives repeatable baseline; varied order belongs to later validation.
        self.queue = deque(list(MOVES)*2+["raise_hands", "walk", "return_guard"]*2+["left_punch", "right_punch"])
        self.move_box.configure(state="disabled")
        self.next_trial()

    def next_trial(self):
        if not self.queue:
            self.cancel_test()
            self.prompt.set("Test tamamlandı.")
            self.feedback.set("Sonuçlar kullanıcı onayına dayanır; teknik uzman değerlendirmesi değildir.")
            self.test_info.set("Sayısal raporu kaydet ile sonuçları saklayabilirsin.")
            self.refresh_stats()
            return
        instruction = self.queue.popleft()
        self.current = Trial(instruction if instruction in MOVES else "none", instruction, stance="neutral")
        self.phase = "prepare"
        self.deadline = perf_counter()+3.
        self.last_trial_sample = self.invalid_since = None
        self.detector.reset("Deneme öncesi ellerini sabit tut.")
        self.yes.configure(state="disabled")
        self.no.configure(state="disabled")
        self.prompt.set("Hazırlan: "+LABELS[instruction])
        self.feedback.set("Başla yazısını bekle. Her denemede yalnızca bir kez yap, sonra elini rahat bırak.")

    def advance_trial(self, now):
        if self.phase == "prepare":
            if now >= self.deadline:
                if self.features and now-self.features.t < .3 and self.detector.state == "ready":
                    self.phase, self.deadline = "active", now+4.
                    self.last_trial_sample = now
                    self.prompt.set("BAŞLA: "+LABELS[self.current.instruction])
                else:
                    self.feedback.set("Başlamak için görünür ve kısa süre sabit eller bekleniyor.")
            self.test_info.set(f"Hazırlık: {max(0, self.deadline-now):.1f} sn · Kalan: {len(self.queue)+1}")
        elif self.phase == "active":
            self.test_info.set(f"Hareket: {max(0, self.deadline-now):.1f} sn")
            if now >= self.deadline:
                if self.last_trial_sample is not None:
                    self.current.max_gap_s = max(self.current.max_gap_s, now-self.last_trial_sample)
                if self.invalid_since is not None:
                    self.current.max_gap_s = max(self.current.max_gap_s, now-self.invalid_since)
                self.phase = "confirm"
                self.prompt.set("İstenen hareketi bir kez yaptın mı?")
                observed = ", ".join(LABELS[x] for x in self.current.events) or "Vuruş algılanmadı"
                self.feedback.set("Gözlenen: "+observed)
                self.test_info.set("Yanlış hareket / birden çok tekrar / erken başlama olduysa Atla seç.")
                self.yes.configure(state="normal")
                self.no.configure(state="normal")

    def confirm(self, performed):
        if self.phase != "confirm":
            return
        self.current.confirmed = performed
        self.trials.append(self.current)
        self.current = None
        self.refresh_stats()
        self.next_trial()

    def refresh_stats(self):
        s = summarize(self.trials)
        pct = lambda v: "—" if v is None else f"%{100*v:.0f}"
        self.stats.set(f"Değerlendirilen: {s['evaluable_trials']} · Belirsiz: {s['unassessable_trials']}\n"
                       f"Atlanan: {s['skipped_trials']} · Kesilen: {s['aborted_trials']}\n"
                       f"Tam doğru vuruş: {pct(s['exact_movement_accuracy'])}\n"
                       f"Kaçan: {s['missed_expected_movements']} · Yanlış sınıf: {s['wrong_class_trials']}\n"
                       f"Negatifte yanlış alarm: {s['false_positive_negative_trials']}/{s['negative_trials']} · Fazladan: {s['extra_events']}")

    def save(self):
        if not self.trials and not self.software_ms:
            self.feedback.set("Henüz kaydedilecek ölçüm yok.")
            return
        try:
            path = save_report(ROOT / "reports", self.trials, "neutral",
                               self.software_ms, self.inference_ms, self.event_ms, self.optical_ms)
            self.feedback.set("Rapor kaydedildi: reports/"+path.name)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Rapor kaydedilemedi", str(exc))

    def add_optical(self):
        value = simpledialog.askfloat("Harici uçtan uca ölçüm", "agents/TEST_PLANI.md yöntemine göre fiziksel vuruş uzanımı →\n"
                                      "ekrandaki hareket adayı bildirimi kaç ms?\nÖlçmediysen İptal seç; tahmini değer girme.",
                                      parent=self.root, minvalue=0., maxvalue=10000.)
        if value is not None:
            if not isfinite(value):
                messagebox.showerror("Geçersiz ölçüm", "Sonlu bir milisaniye değeri girin.")
                return
            self.optical_ms = value
            self.feedback.set(f"Kullanıcının harici ölçümü: {value:.1f} ms. Sonraki rapora eklenecek.")

    def tick(self):
        if self.closed:
            return
        try:
            now = perf_counter()
            if self.auto_start and not self.camera and now >= self.retry_at:
                self.start_automatic()
            if self.camera:
                if self.camera.error:
                    reason = self.camera.error
                    self.stop_camera("camera_error")
                    self.status.set(reason)
                    self.retry_at = perf_counter()+5.
                else:
                    sample = self.camera.read()
                    if sample and sample[0] != self.last_sequence:
                        self.last_sequence, received, frame = sample
                        self.last_frame_time = received
                        if now-received <= .25:
                            self.process_frame(frame, received)
                        else:
                            self.invalidate_tracking(now, "Kamera karesi eski; değerlendirilemiyor.")
                    elif now-max(self.last_frame_time, self.camera_opened_at) > .3:
                        self.invalidate_tracking(now, "Yeni kamera karesi bekleniyor; değerlendirilemiyor.")
            self.advance_trial(perf_counter())
            # Consume the latest capture first. An older Features sample must not
            # briefly pause Godot when a fresh frame is already waiting this tick.
            self.sync_tower()
            if self.report:
                self.report.flush()
        except Exception as exc:
            self.stop_camera("processing_error")
            self.status.set("İşleme durduruldu: "+str(exc))
            self.retry_at = perf_counter()+5.
        self.root.after(8, self.tick)

    def sync_tower(self):
        """The live UI and outgoing readiness use the same current observation."""
        if not self.tower_client:
            return
        f = self.features
        if not self.camera:
            reason = "Kamera kapalı."
        elif not self.detector:
            reason = "Kalibrasyon bekleniyor."
        elif f is None or not 0 <= perf_counter()-f.t <= .25:
            reason = "Güncel kamera karesi bekleniyor."
        elif not (f.valid or f.body_tracked):
            reason = f.reason or "Gerekli eklemlerin görünmesi bekleniyor."
        else:
            reason = ""
        guard = bool(not reason and self.detector.state == "ready" and self.detector.in_guard(f))
        self.tower_client.poll(ready=not reason, guard=guard)
        self.tower_status.set("Kule için takip hazır değil · " + reason if reason else
                              ("Gövde takibi sürüyor · " + f.reason if not f.valid else self.tower_client.status))
        if self.report:
            self.consume_diagnostics()
            live = self.status.get()
            if self.calibration and not self.detector:
                live = f"Hazırlık %{self.progress.get()*100:.0f} · " + live
            fps = ((len(self.frame_times)-1)/(self.frame_times[-1]-self.frame_times[0])
                   if len(self.frame_times) > 1 and self.frame_times[-1] > self.frame_times[0] else 0.)
            live += f" · {fps:.1f} FPS"
            if self.report.error:
                live = self.report.error
            elif self.report.dropped:
                live += " · Rapor olay sınırına ulaştı"
            elif self.report.images >= self.report.MAX_IMAGES:
                live += " · Görsel sınırına ulaştı"
            self.tower_client.publish_diagnostic(live, self.delivery_status or self.last_detection.get(), self.report.record_frames)
            state = reason or self.status.get()
            if state != self.report_status:
                now = perf_counter()
                evidence = bool(f and not f.valid and now-self.last_tracking_evidence >= 5.)
                self.report.add("tracking", state, attempt=self.attempt if self.active_attempt else 0, evidence=evidence)
                if evidence:
                    self.last_tracking_evidence = now
                self.report_status = state

    def consume_diagnostics(self):
        titles = {"sent": "Oyun sonucu bekleniyor", "send_failed": "Vuruş gönderilemedi",
                  "unconfirmed": "Oyun onayı alınmadı; sonuç bilinmiyor", "no_context": "Oyun bağlantısı yok",
                  "not_ready": "Takip hazır olmadığı için gönderilmedi", "paused": "Oyun duraklatılmış",
                  "not_fighting": "Karşılaşma başlamadığı için gönderilmedi", "stale_context": "Oyun bilgisi güncel değil",
                  "motion_context_or_time_invalid": "Hareket sırasında oyun bağlamı değişti veya zaman bilgisi geçersiz",
                  "hit": "Oyun vuruşu puanladı", "defeated": "Oyun vuruşu puanladı; muhafız yenildi",
                  "wrong": "Hareket tanındı; istenen hareketle eşleşmedi", "inactive": "Oyun aktif olmadığı için reddetti",
                  "duplicate": "Oyun yinelenen olayı reddetti", "late": "Oyun geç olayı reddetti",
                  "stale_prompt": "Oyun eski hedefe ait olayı reddetti", "stale_lease": "Oyun güncel olmayan olayı reddetti"}
        while self.tower_client.diagnostics:
            item = self.tower_client.diagnostics.popleft()
            event = item["event"]
            attempt = self.event_attempts.get(event, self.attempt)
            self.delivery_status = LABELS.get(item["move"], item["move"]) + " · " + titles.get(item["outcome"], item["outcome"])
            self.report.add(item["kind"], self.delivery_status, detail=item["outcome"],
                            move=item["move"], expected=item["expected"], event=event, attempt=attempt)
            if item["kind"] == "game" or item["outcome"] == "unconfirmed":
                self.event_attempts.pop(event, None)
        while self.tower_client.commands:
            action = self.tower_client.commands.popleft()
            if action.startswith("frames_"):
                self.report.set_frames(action == "frames_on")
            elif action == "calibrate":
                self.calibrate()

    def record_detection(self, previous_state, hit=None):
        if not self.report or not self.detector:
            return
        d = self.detector
        expected = (self.tower_client.context["move"] if self.tower_client and self.tower_client.context else
                    next((m for m in MOVES if LABELS[m] == self.requested.get()), ""))
        if d.attempt_started:
            self.attempt += 1
            self.active_attempt = True
            self.last_attempt_checks = {}
            self.last_attempt_measures = {}
            self.delivery_status = ""
            self.report.add("attempt", "Hareket başladı", attempt=self.attempt, expected=expected)
        # Quantized progress changes are useful even when every boolean is still
        # false. Frame timing alone must not create a per-frame report stream.
        progress = {key: value for key, value in d.measures.items() if key != "kare_araligi_ms"}
        if self.active_attempt and (d.checks != self.last_attempt_checks or progress != self.last_attempt_measures):
            self.report.add("motion", d.reason, attempt=self.attempt, checks=d.checks, measures=d.measures, expected=expected)
            self.last_attempt_checks = d.checks
            self.last_attempt_measures = progress
        if hit:
            self.report.add("detected", "Algılandı: " + LABELS[hit.move], detail="Ardışık karelerde hareket yönü doğrulandı; teknik gard aranmadı",
                            move=hit.move, attempt=self.attempt, checks=d.checks, measures=d.measures, evidence=True, expected=expected)
            self.active_attempt = False
        elif self.active_attempt and d.state == "settling":
            self.report.add("rejected", d.last_result or d.reason, attempt=self.attempt, checks=d.checks, measures=d.measures, evidence=True, expected=expected)
            self.active_attempt = False

    def invalidate_tracking(self, now, reason):
        self.status.set(reason)
        self.features = Features(now, {}, (0., 0.), 0., False, False, reason)
        self.sync_tower()
        if self.detector:
            previous_state = self.detector.state
            self.detector.update(self.features)
            self.last_detection.set(self.detector.last_result)
            self.record_detection(previous_state)
        if self.calibration and not self.calibration.baseline:
            self.calibration.samples.clear()
            self.progress.set(0.)
        if self.phase == "active" and self.invalid_since is None:
            self.invalid_since = self.last_trial_sample if self.last_trial_sample is not None else now
        self.video.configure(image="", text="Güncel kamera görüntüsü bekleniyor", width=80, height=28)
        self.video.image = None

    def process_frame(self, frame, received):
        self.frame_times.append(received)
        begin = perf_counter()
        landmarks, world = self.pose.process(frame, received)
        self.inference_ms.append((perf_counter()-begin)*1000)
        f = extract(landmarks, world, received)
        if perf_counter()-received > .25:
            f = Features(received, {}, (0., 0.), 0., False, False, "İşleme gecikmesi yüksek; değerlendirilemiyor.")
        self.features = f
        if self.report:
            self.report.observe(frame, valid=f.valid, body=f.valid or f.body_tracked, guard=f.guard)
        hit = None
        if self.calibration and not self.calibration.baseline:
            self.progress.set(self.calibration.update(f))
            self.status.set("Eller görünüyor; kısa bir an sabit kal." if f.valid else f.reason)
            if self.calibration.baseline:
                self.detector = Detector(self.calibration.baseline)
                if self.report:
                    self.report.add("calibration", "Hazırlık tamamlandı", detail="neutral")
                self.prompt.set("Hareket isteği kule ekranında gösterilir." if self.tower_client else self.requested.get())
                self.feedback.set("Kalibrasyon tamamlandı. Kule otomatik başlayacak." if self.tower_client else
                                  "Kalibrasyon tamamlandı. Serbest dene veya etiketli testi başlat.")
        elif self.detector:
            previous_state = self.detector.state
            hit = self.detector.update(f)
            self.record_detection(previous_state, hit)
            self.status.set(self.detector.reason)
            self.last_detection.set(self.detector.last_result)
        else:
            self.status.set("Kadraja yerleş; Kalibre et düğmesine bas." if f.valid else f.reason)
        if self.tower_client:
            started_t = self.detector.started if hit else None
            self.sync_tower()
            if hit:
                sent = self.tower_client.send_hit(hit, started_t)
                if self.report:
                    if sent:
                        self.event_attempts[self.tower_client.event] = self.attempt
                    self.consume_diagnostics()
        if self.phase == "active" and self.current and received <= self.deadline:
            trial = self.current
            trial.frames += 1
            trial.valid_frames += int(f.valid)
            if self.last_trial_sample is not None:
                trial.max_gap_s = max(trial.max_gap_s, received-self.last_trial_sample)
                if received > self.last_trial_sample:
                    trial.frame_intervals_ms.append((received-self.last_trial_sample)*1000)
            self.last_trial_sample = received
            if not f.valid and self.invalid_since is None:
                self.invalid_since = received
            if f.valid and self.invalid_since is not None:
                trial.max_gap_s = max(trial.max_gap_s, received-self.invalid_since)
                self.invalid_since = None
            if hit:
                trial.events.append(hit.move)
                trial.return_ms.append((hit.confirmed_t-hit.peak_t)*1000)
        if hit and self.tower_client:
            self.feedback.set("Algılanan: "+LABELS[hit.move]+" · sonuç kule ekranında.")
        elif hit and self.phase in ("idle", "active"):
            desired = self.current.expected if self.phase == "active" else next(m for m in MOVES if LABELS[m] == self.requested.get())
            self.feedback.set(("Eşleşti: " if hit.move == desired else "Algılanan farklı: ")+LABELS[hit.move]+
                              " · hareket yönü doğrulandı")
        if not self.integrated:
            pixels = preview(frame, landmarks)
            picture = ImageTk.PhotoImage(Image.fromarray(pixels).resize((640, 480)))
            self.video.configure(image=picture, text="", width=640, height=480)
            self.video.image = picture
            self.root.update_idletasks()
        if self.report and received-self.last_sample_report >= 1.:
            self.report.add("sample", self.status.get(), detail=f"Görünür: {f.valid}; gövde: {f.body_tracked}",
                            attempt=self.attempt if self.active_attempt else 0,
                            checks=self.detector.checks if self.detector and f.valid and self.detector.state == "outbound" else None)
            self.last_sample_report = received
        latency = (perf_counter()-received)*1000
        self.software_ms.append(latency)
        if hit and self.phase in ("idle", "active"):
            self.event_ms.append(latency)
        if len(self.software_ms) % 10 == 0:
            ordered = sorted(self.software_ms)
            p95 = ordered[min(len(ordered)-1, int(len(ordered)*.95))]
            fps = (len(self.frame_times)-1)/(self.frame_times[-1]-self.frame_times[0]) if len(self.frame_times) > 1 else 0.
            self.timings.set(f"Kare alımı → arayüze gönderim: {latency:.0f} ms · p95 {p95:.0f} ms\n"
                             f"Model: {self.inference_ms[-1]:.0f} ms · {fps:.1f} FPS · Kamera: {self.camera.backend}\n"
                             + ("Düşük FPS: daha iyi ışık kısa hareket takibini iyileştirebilir.\n" if fps < 15 else "")+
                             "Sensör ve fiziksel ekran gecikmesi bu ölçüme dahil değil.")

    def close(self):
        if self.closed:
            return
        # Automatic recognition journal closes alongside the owned camera.
        self.closed = True
        self.stop_camera("app_closed")
        if self.report:
            self.report.close()
        if self.tower_client:
            self.tower_client.close()
        self.root.destroy()

    def run(self):
        self.root.mainloop()
