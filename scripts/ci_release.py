"""Fail-closed release checks; stage only the tested public Windows package."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from shadowmma import __version__


def validate_tag(tag, version):
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag) or tag != f"v{version}":
        raise ValueError(f"Release tag must equal v{version}; received {tag!r}")


def validate_package(manifest, verification, commit):
    if manifest.get("source_commit") != commit or manifest.get("source_dirty") is not False:
        raise ValueError("Package must come from this clean Git commit")
    if verification.get("camera_opened") is not False:
        raise ValueError("Package validation must keep the physical camera closed")
    checks = verification.get("checks", [])
    if verification.get("passed", 0) < 14 or verification.get("passed") != len(checks):
        raise ValueError("Full Windows package validation must pass before upload")


def check_ref():
    if os.environ.get("GITHUB_REF_TYPE") == "tag":
        validate_tag(os.environ.get("GITHUB_REF_NAME", ""), __version__)
        subprocess.run(["git", "merge-base", "--is-ancestor", "HEAD", "origin/main"], cwd=ROOT, check=True)
        print(f"Validated release tag v{__version__} on main history")
    else:
        print("Manual build: package artifact only; no Release will be published")


def stage():
    paths = json.loads((ROOT / "build/latest-package.json").read_text(encoding="utf-8"))
    archive = Path(paths["zip"]).resolve()
    if not archive.is_relative_to((ROOT / "dist").resolve()):
        raise ValueError("Package must be inside this checkout's dist directory")
    if archive.name != "ShadowMMA-Windows-x64.zip":
        raise ValueError("Unexpected release archive name")
    verification = json.loads((ROOT / "build/package-validation.json").read_text(encoding="utf-8"))
    if Path(verification["package"]).resolve() != archive:
        raise ValueError("Validation belongs to a different package")
    with zipfile.ZipFile(archive) as bundle:
        manifest = json.loads(bundle.read("ShadowMMA/manifest.json"))
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    validate_package(manifest, verification, commit)
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    checksum = archive.with_suffix(".zip.sha256")
    expected = f"{digest}  {archive.name}"
    if checksum.read_text(encoding="ascii").strip() != expected:
        raise ValueError("Package checksum does not match")
    destination = ROOT / "build/ci-release"
    destination.mkdir(exist_ok=False)
    shutil.copy2(archive, destination / archive.name)
    shutil.copy2(checksum, destination / checksum.name)
    notes = (
        f"Experimental Computer Vision MMA Training Game / ShadowMMA {__version__}\n\n"
        "Extract the entire ZIP and open ShadowMMA.exe. It opens the webcam automatically.\n"
        "Use ShadowMMA.exe --launcher to choose keyboard or synthetic input instead.\n\n"
        "Real movement recognition remains unreliable. Low effective FPS is a suspected\n"
        "contributor, not an isolated root cause. Automated checks use generated observations\n"
        "and do not establish human recognition accuracy. The interface is primarily Turkish.\n\n"
        "This is an unsigned experimental Windows x64 build, not a validated coaching product.\n"
        "Reports are stored locally; optional event images are disabled by default.\n\n"
        f"Source commit: {commit}\nSHA256: {digest}\n"
    )
    (destination / "RELEASE_NOTES.md").write_text(notes, encoding="utf-8")
    print(f"Verified Windows package staged: {destination}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("check-ref", "stage"))
    args = parser.parse_args()
    {"check-ref": check_ref, "stage": stage}[args.command]()
