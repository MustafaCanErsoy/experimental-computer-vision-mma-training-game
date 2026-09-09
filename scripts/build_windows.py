"""Offline, pinned Windows one-folder build; no global installs or network calls."""
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from shadowmma.assets import MODEL, MODEL_SHA256, validate_model
from shadowmma.paths import GODOT
from setup_godot import SHA256 as GODOT_ZIP_SHA


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def locked_distributions():
    found = {}
    for lock in ("requirements.lock.txt", "requirements-build.lock.txt"):
        for line in (ROOT / lock).read_text().splitlines():
            if not line or line.startswith("#"):
                continue
            name, version = line.split("==")
            dist = metadata.distribution(name)
            if dist.version != version:
                raise RuntimeError(f"Version mismatch: {name}: expected {version}, got {dist.version}")
            found[name] = dist
    return found


def copy_licenses(package, distributions):
    licenses = package / "agents/licenses"
    shutil.copytree(ROOT / "agents/licenses", licenses)
    inventory = []
    for name, dist in distributions.items():
        target = licenses / name
        target.mkdir(exist_ok=True)
        files = []
        for entry in dist.files or []:
            lower = entry.name.lower()
            if lower.startswith(("license", "copying", "notice", "copyright", "authors")) and entry.suffix not in (".py", ".pyc", ".xml"):
                source = Path(dist.locate_file(entry))
                if source.is_file():
                    output = target / str(entry).replace("/", "__").replace("\\", "__")
                    shutil.copy2(source, output)
                    files.append(str(output.relative_to(package)))
        # FlatBuffers' wheel omits LICENSE; its pinned upstream license is vendored.
        if not files and name == "flatbuffers":
            files.append("agents/licenses/flatbuffers-LICENSE.txt")
        if not files:
            raise RuntimeError(f"Missing license text: {name}")
        inventory.append({"name": name, "version": dist.version, "licenses": files})
    shutil.copy2(Path(sys.base_prefix) / "LICENSE.txt", licenses / "Python-LICENSE.txt")
    shutil.copy2(Path(sys.base_prefix) / "tcl/tk8.6/license.terms", licenses / "Tk-license.terms")
    subprocess.run([str(GODOT), "--headless", "--path", str(ROOT / "godot"), "--script",
                    str(ROOT / "scripts/godot_licenses.gd"), "--", str(licenses / "Godot-licenses.json")],
                   check=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    (licenses / "inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    return inventory


def main():
    if os.name != "nt" or sys.version_info[:2] != (3, 12):
        raise RuntimeError("Build with Windows x64 Python 3.12 in the pinned project venv.")
    distributions = locked_distributions()
    validate_model()
    archive = ROOT / ".tools/godot/godot.zip"
    if sha(archive) != GODOT_ZIP_SHA:
        raise RuntimeError("Godot archive SHA256 mismatch")
    with zipfile.ZipFile(archive) as bundle:
        if hashlib.sha256(bundle.read(GODOT.name)).hexdigest() != sha(GODOT):
            raise RuntimeError("Godot executable differs from verified archive")
    for item in json.loads((ROOT / "agents/licenses/sources.json").read_text()):
        if sha(ROOT / "agents/licenses" / item["file"]) != item["sha256"]:
            raise RuntimeError(f"License source hash mismatch: {item['file']}")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    build = ROOT / "build" / f"windows-{stamp}"
    output = ROOT / "dist" / f"windows-{stamp}"
    build.mkdir(parents=True)
    output.mkdir(parents=True)
    log = build / "packaging-build.log"
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--windowed", "--onedir",
               "--name", "ShadowMMA", "--paths", str(ROOT), "--specpath", str(build),
               "--workpath", str(build / "work"), "--distpath", str(output),
               "--collect-all", "mediapipe", "--collect-all", "sounddevice",
               "--exclude-module", "mediapipe.tasks.python.test",
               "--exclude-module", "pytest", "--exclude-module", "IPython",
               str(ROOT / "scripts/windows_entry.py")]
    print(f"Building; log: {log}", flush=True)
    with log.open("w", encoding="utf-8") as stream:
        subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, check=True)
    package = output / "ShadowMMA"
    (package / "runtime/godot").mkdir(parents=True)
    shutil.copy2(GODOT, package / "runtime/godot" / GODOT.name)
    (package / "godot").mkdir()
    for entry in (ROOT / "godot").iterdir():
        if entry.is_file() and not entry.name.startswith("test_") and entry.suffix in (".gd", ".tscn", ".godot", ".uid"):
            shutil.copy2(entry, package / "godot" / entry.name)
    (package / "assets").mkdir()
    shutil.copy2(MODEL, package / "assets" / MODEL.name)
    (package / "agents").mkdir()
    for name in ("PAKET.md", "RAPORLAMA.md", "TEST_PLANI.md"):
        shutil.copy2(ROOT / "agents" / name, package / "agents" / name)
    if (ROOT / "agents/CI_CD.md").is_file():
        shutil.copy2(ROOT / "agents/CI_CD.md", package / "agents/CI_CD.md")
    (package / "Raporlar.cmd").write_text('@echo off\n"%~dp0ShadowMMA.exe" --reports\n', encoding="ascii")
    inventory = copy_licenses(package, distributions)
    manifest = {"schema": 1, "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "source_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)),
                "python": sys.version, "model_sha256": MODEL_SHA256, "dependencies": inventory,
                "files": {str(p.relative_to(package)).replace("\\", "/"): sha(p) for p in sorted(package.rglob("*")) if p.is_file()}}
    (package / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    zip_path = Path(shutil.make_archive(str(output / "ShadowMMA-Windows-x64"), "zip", output, "ShadowMMA"))
    zip_path.with_suffix(".zip.sha256").write_text(f"{sha(zip_path)}  {zip_path.name}\n", encoding="ascii")
    (ROOT / "build/latest-package.json").write_text(json.dumps({"folder": str(package), "zip": str(zip_path), "log": str(log)}, indent=2), encoding="utf-8")
    print(f"Package: {zip_path}", flush=True)


if __name__ == "__main__":
    main()
