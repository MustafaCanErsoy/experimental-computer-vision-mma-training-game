"""Shared local asset manifest. Importing it needs no vision dependencies."""
import hashlib
from .paths import ROOT
MODEL = ROOT / "assets" / "pose_landmarker_lite.task"
MODEL_SHA256 = "59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a"
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"


def validate_model(path=MODEL):
    if not path.is_file():
        raise FileNotFoundError("Yerel model eksik. Kurulum.cmd dosyasini calistirin.")
    if hashlib.sha256(path.read_bytes()).hexdigest() != MODEL_SHA256:
        raise ValueError("Yerel model bozuk veya surumu farkli. Kurulum.cmd ile onarin.")
