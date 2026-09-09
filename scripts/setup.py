"""Download model at setup only; pinned hash, atomic install, project-local files."""
import hashlib
from pathlib import Path
import urllib.request
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from shadowmma.assets import MODEL, MODEL_SHA256 as SHA, MODEL_URL as URL


def main():
    MODEL.parent.mkdir(exist_ok=True)
    if MODEL.exists() and hashlib.sha256(MODEL.read_bytes()).hexdigest() == SHA:
        print("Yerel model dogrulandi.")
        return
    temporary = MODEL.with_suffix(".part")
    try:
        with urllib.request.urlopen(URL, timeout=60) as response, temporary.open("wb") as out:
            while block := response.read(1024*1024):
                out.write(block)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != SHA:
            raise RuntimeError("Model SHA256 uyusmuyor; model yuklenmedi.")
        temporary.replace(MODEL)
        print("Yerel model indirildi ve SHA256 dogrulandi.")
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
