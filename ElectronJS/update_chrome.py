"""Copy an installed Chrome into EasySpider's bundle for Playwright.

Run from any directory. --source accepts the Chrome installation directory
(or Google Chrome.app on macOS). Existing executors and launchers are retained.
"""
import argparse
import os
from pathlib import Path
import platform
import shutil
import sys


def main():
    root = Path(__file__).resolve().parent
    if sys.platform == "win32":
        arch = "win64" if platform.architecture()[0] == "64bit" else "win32"
        candidates = [Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application",
                      Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application"]
        source = next((p for p in candidates if (p / "chrome.exe").is_file()), candidates[0])
        binary = Path("chrome.exe")
        target = root / ("chrome_" + arch)
        launcher = "execute_" + arch + ".bat"
    elif sys.platform == "darwin":
        source = Path("/Applications/Google Chrome.app")
        target = root / "chrome_mac64.app"
        binary = Path("Contents/MacOS/Google Chrome")
        launcher = None
    elif sys.platform == "linux":
        source = Path("/opt/google/chrome")
        target = root / "chrome_linux64"
        binary = Path("chrome")
        launcher = "execute_linux64.sh"
    else:
        raise SystemExit("Unsupported platform: " + sys.platform)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=source)
    args = parser.parse_args()
    source = args.source.expanduser().resolve()
    if not (source / binary).is_file():
        parser.error("Chrome binary not found: " + str(source / binary))
    if source == target.resolve() or target.resolve().is_relative_to(source) or source.is_relative_to(target.resolve()):
        parser.error("Source and bundled Chrome directories must be separate")
    shutil.copytree(source, target, dirs_exist_ok=True, symlinks=True)
    if launcher and (root / launcher).is_file():
        shutil.copy2(root / launcher, target / launcher)
    if (root / "stealth.min.js").is_file() and sys.platform != "darwin":
        shutil.copy2(root / "stealth.min.js", target / "stealth.min.js")
    if sys.platform != "win32":
        (target / binary).chmod(0o755)
        if launcher:
            (target / launcher).chmod(0o755)
    print("Chrome copied to", target)
    print("Rebuild the Playwright execution stage with the platform build script.")


if __name__ == "__main__":
    main()
