"""Build and package on the native target system."""
import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import __version__ as VERSION


def run(*args):
    subprocess.run([str(a) for a in args], cwd=ROOT, check=True)


def build():
    args = ["flet", "pack", "main.py", "--name", "Vocaflop", "--yes"]
    if sys.platform == "win32":
        args += ["--onedir", "--icon", "assets/logo.ico", "--product-name", "VocaFlop Media Downloader", "--file-version", VERSION + ".0", "--product-version", VERSION + ".0"]
    elif sys.platform == "darwin":
        args += ["--icon", "assets/logo.icns", "--bundle-id", "io.github.onion7654321.vocaflopmedia", "--product-name", "VocaFlop Media Downloader", "--product-version", VERSION]
    run(*args)
    if sys.platform.startswith("linux"):
        output = ROOT / "dist" / "Vocaflop"
        if output.is_file():
            temporary = output.with_name("Vocaflop.bin")
            output.rename(temporary)
            output.mkdir()
            temporary.rename(output / "Vocaflop")


def package():
    release = ROOT / "release"
    release.mkdir(exist_ok=True)
    dist = ROOT / "dist"
    arch = platform.machine().lower()
    if sys.platform == "win32":
        from package_release import package as portable
        portable(ROOT)
        iscc = shutil.which("ISCC") or str(Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe")
        run(iscc, f"/DVersion={VERSION}", "packaging/windows.iss")
    elif sys.platform == "darwin":
        app = dist / "Vocaflop.app"
        if not app.is_dir():
            raise FileNotFoundError(app)
        tag = "ARM64" if arch in {"arm64", "aarch64"} else "Intel"
        staging = ROOT / "build" / "dmg-stage"
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        run("ditto", app, staging / "Vocaflop.app")
        (staging / "Applications").symlink_to("/Applications")
        run("hdiutil", "create", "-ov", "-volname", "VocaFlopMedia", "-srcfolder", staging, "-format", "UDZO", release / f"Vocaflop-{VERSION}-macOS-{tag}.dmg")
    elif sys.platform.startswith("linux"):
        run("bash", "scripts/package_linux.sh", VERSION)
    else:
        raise RuntimeError("Unsupported platform")
    run(sys.executable, "scripts/release_checksums.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-only", action="store_true")
    args = parser.parse_args()
    if not args.package_only:
        run(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q")
        build()
    package()
