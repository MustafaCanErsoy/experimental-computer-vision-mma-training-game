"""Local-only capture and MediaPipe adapter. Frames exist only in RAM."""
from threading import Thread, Lock, Event
from time import perf_counter
import cv2
import mediapipe as mp
from .assets import ROOT, MODEL, MODEL_SHA256, validate_model

CONNECTIONS = ((11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
               (11, 23), (12, 24), (23, 24))


class Camera:
    """Single latest-frame slot avoids accumulating old frames during inference."""
    def __init__(self, index=0, mjpg=False):
        self.index = index
        self.mjpg = mjpg
        self.lock = Lock()
        self.stop = Event()
        self.latest = None
        self.error = ""
        self.backend = "opening"
        self.thread = Thread(target=self._capture, daemon=True)
        self.thread.start()

    def _capture(self):
        try:
            sequence = 0
            for backend in (cv2.CAP_DSHOW, cv2.CAP_MSMF):
                if self.stop.is_set():
                    return
                cap = cv2.VideoCapture(self.index, backend)
                try:
                    if not cap.isOpened():
                        continue
                    if self.mjpg:
                        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    cap.set(cv2.CAP_PROP_FPS, 30)
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # advisory; driver may ignore
                    failures = 0
                    while not self.stop.is_set():
                        ok, frame = cap.read()
                        received = perf_counter()
                        if not ok:
                            failures += 1
                            if failures >= 10:
                                break
                            self.stop.wait(.03)
                            continue
                        failures = 0
                        sequence += 1
                        self.backend = cap.getBackendName()
                        with self.lock:
                            self.latest = (sequence, received, frame)
                finally:
                    cap.release()
                if self.stop.is_set():
                    return
            self.error = "Kamera açılamadı / bağlantı kesildi. Kamera numarasını, Windows kamera iznini ve diğer uygulamaları kontrol et."
        except Exception as exc:
            self.error = f"Kamera hatası: {exc}"

    def read(self):
        with self.lock:
            return self.latest

    def close(self):
        self.stop.set()
        self.thread.join(timeout=1.)


class Pose:
    def __init__(self):
        validate_model()
        self.landmarker = mp.tasks.vision.PoseLandmarker.create_from_options(
            mp.tasks.vision.PoseLandmarkerOptions(
                # Native file loading fails on some Unicode Windows paths.
                # Python reads the verified offline bytes without a second path decoder.
                base_options=mp.tasks.BaseOptions(model_asset_buffer=MODEL.read_bytes()),
                running_mode=mp.tasks.vision.RunningMode.VIDEO,
                num_poses=1, min_pose_detection_confidence=.6,
                min_pose_presence_confidence=.6, min_tracking_confidence=.6))
        self.last_ms = -1

    def process(self, frame, received):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        ms = max(self.last_ms+1, int(received*1000))
        self.last_ms = ms
        result = self.landmarker.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ms)
        if result.pose_landmarks and result.pose_world_landmarks:
            return result.pose_landmarks[0], result.pose_world_landmarks[0]
        return [], []

    def close(self):
        self.landmarker.close()


def preview(frame, landmarks):
    canvas = frame.copy()
    h, w = canvas.shape[:2]
    for a, b in CONNECTIONS:
        if landmarks and min(landmarks[a].visibility, landmarks[b].visibility) > .65:
            pa, pb = landmarks[a], landmarks[b]
            cv2.line(canvas, (int(pa.x*w), int(pa.y*h)), (int(pb.x*w), int(pb.y*h)), (160, 235, 80), 2)
    # Mirror presentation only. Anatomical left/right in inference remain unchanged.
    canvas = cv2.flip(canvas, 1)
    cv2.rectangle(canvas, (int(w*.15), int(h*.08)), (int(w*.85), int(h*.94)), (130, 145, 160), 1)
    return cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
