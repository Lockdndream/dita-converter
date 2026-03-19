"""
build/build.py
DITA Converter Tool — Build Script

Run this from the project root on a Windows machine:

    python build/build.py

What it does:
  1. Checks Python version and required tools
  2. Installs / upgrades PyInstaller
  3. Cleans previous build artefacts
  4. Runs PyInstaller with the spec file
  5. Reports the output exe size and location
  6. (Optional) Signs the exe if signtool.exe is on PATH

Session: S-10
"""

import os
import sys
import shutil
import subprocess
import argparse
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────

ROOT      = Path(__file__).parent.parent
BUILD_DIR = ROOT / "build"
DIST_DIR  = ROOT / "dist"
WORK_DIR  = ROOT / "build" / "_pyinstaller_work"
SPEC_FILE = BUILD_DIR / "dita_converter.spec"
EXE_OUT   = DIST_DIR / "DITAConverter.exe"

# ── Colours (Windows supports ANSI in modern terminals) ───────────────────────

GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
RESET  = "\033[0m"

def ok(msg):   print(f"{GREEN}✅ {msg}{RESET}")
def warn(msg): print(f"{YELLOW}⚠️  {msg}{RESET}")
def err(msg):  print(f"{RED}❌ {msg}{RESET}")
def info(msg): print(f"   {msg}")


# ── Checks ───────────────────────────────────────────────────────────────────

def check_python():
    v = sys.version_info
    if v < (3, 11):
        err(f"Python 3.11+ required. Found {v.major}.{v.minor}.")
        sys.exit(1)
    ok(f"Python {v.major}.{v.minor}.{v.micro}")


def check_pip_package(name: str) -> bool:
    result = subprocess.run(
        [sys.executable, "-m", "pip", "show", name],
        capture_output=True
    )
    return result.returncode == 0


def install_pyinstaller():
    if check_pip_package("pyinstaller"):
        ok("PyInstaller already installed")
        return
    info("Installing PyInstaller...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "pyinstaller", "--quiet"],
        check=True
    )
    ok("PyInstaller installed")


def check_dependencies():
    required = ["pdfplumber", "docx", "yaml", "lxml", "streamlit"]
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        err(f"Missing packages: {', '.join(missing)}")
        info("Run: pip install -r requirements.txt")
        sys.exit(1)
    ok("All dependencies present")


# ── Clean ─────────────────────────────────────────────────────────────────────

def clean():
    for d in [DIST_DIR, WORK_DIR]:
        if d.exists():
            shutil.rmtree(d)
            info(f"Cleaned: {d}")
    ok("Previous build artefacts removed")


# ── Build ─────────────────────────────────────────────────────────────────────

def build():
    info(f"Spec file: {SPEC_FILE}")
    info(f"Output:    {EXE_OUT}")
    print()

    cmd = [
        sys.executable, "-m", "PyInstaller",
        str(SPEC_FILE),
        "--distpath", str(DIST_DIR),
        "--workpath", str(WORK_DIR),
        "--noconfirm",
        "--clean",
    ]

    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        err("PyInstaller build failed. See output above.")
        sys.exit(1)

    if not EXE_OUT.exists():
        err(f"Expected exe not found at: {EXE_OUT}")
        sys.exit(1)

    size_mb = EXE_OUT.stat().st_size / (1024 * 1024)
    ok(f"Build complete — {EXE_OUT.name} ({size_mb:.1f} MB)")
    return EXE_OUT


# ── Sign ──────────────────────────────────────────────────────────────────────

def sign(exe_path: Path, cert_path: str, cert_password: str, timestamp_url: str):
    """
    Sign the exe using signtool.exe (Windows SDK).
    cert_path     — path to your .pfx certificate file
    cert_password — password for the .pfx file
    timestamp_url — RFC 3161 timestamp server URL
    """
    signtool = shutil.which("signtool")
    if not signtool:
        # Try common SDK locations
        candidates = [
            r"C:\Program Files (x86)\Windows Kits\10\bin\x64\signtool.exe",
            r"C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x64\signtool.exe",
        ]
        for c in candidates:
            if Path(c).exists():
                signtool = c
                break

    if not signtool:
        warn("signtool.exe not found — skipping signing.")
        warn("Install Windows SDK or add signtool to PATH.")
        return

    cmd = [
        signtool, "sign",
        "/f",  cert_path,
        "/p",  cert_password,
        "/fd", "SHA256",
        "/tr", timestamp_url,
        "/td", "SHA256",
        "/v",
        str(exe_path),
    ]

    info(f"Signing with: {cert_path}")
    result = subprocess.run(cmd)
    if result.returncode == 0:
        ok("Exe signed successfully")
    else:
        err("Signing failed — see output above.")
        warn("Unsigned exe is still at: " + str(exe_path))


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Build DITAConverter.exe")
    parser.add_argument("--sign",          action="store_true", help="Sign the exe after build")
    parser.add_argument("--cert",          default="",          help="Path to .pfx certificate")
    parser.add_argument("--cert-password", default="",          help="Certificate password")
    parser.add_argument("--timestamp-url", 
                        default="http://timestamp.digicert.com",
                        help="RFC 3161 timestamp server URL")
    args = parser.parse_args()

    print()
    print("=" * 50)
    print("  DITA Converter — Build Script")
    print("=" * 50)
    print()

    check_python()
    install_pyinstaller()
    check_dependencies()
    clean()

    print()
    info("Running PyInstaller...")
    print()

    exe_path = build()

    if args.sign:
        if not args.cert:
            err("--cert required when using --sign")
            sys.exit(1)
        print()
        sign(exe_path, args.cert, args.cert_password, args.timestamp_url)

    print()
    print("=" * 50)
    print(f"  Output: {exe_path}")
    print("=" * 50)
    print()
    info("Next steps:")
    info("  1. Test: double-click dist\\DITAConverter.exe")
    info("  2. Sign: python build/build.py --sign --cert path\\to\\cert.pfx")
    info("  3. Upload to SharePoint for distribution")
    print()


if __name__ == "__main__":
    main()
