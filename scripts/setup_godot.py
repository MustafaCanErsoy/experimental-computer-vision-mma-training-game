"""Install a pinned portable Godot inside this project; network used only here."""
import hashlib
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent.parent
VERSION = "4.7.2"
SHA256 = "731980f9608d61333e5baf54a2ef17210acc7a538446c0cb9969f002aca1e953"
URL = f"https://github.com/godotengine/godot-builds/releases/download/{VERSION}-stable/Godot_v{VERSION}-stable_win64.exe.zip"
INSTALL = ROOT / ".tools" / "godot"
EXE = INSTALL / f"Godot_v{VERSION}-stable_win64.exe"


def main():
    INSTALL.mkdir(parents=True, exist_ok=True)
    archive = INSTALL / "godot.zip"
    with urllib.request.urlopen(URL, timeout=60) as response, archive.open("wb") as stream:
        while block := response.read(1024*1024):
            stream.write(block)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        raise RuntimeError("Godot archive hash mismatch; not extracted")
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            destination = (INSTALL / member.filename).resolve()
            if not destination.is_relative_to(INSTALL.resolve()):
                raise RuntimeError("Unsafe archive path")
        bundle.extractall(INSTALL)
    if not EXE.is_file():
        raise RuntimeError("Godot executable missing")
    print(f"Godot {VERSION} installed in .tools/godot; SHA256 verified.")


if __name__ == "__main__":
    main()
