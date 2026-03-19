# dita_converter.spec
# PyInstaller spec file for DITA Converter Tool
#
# Run from the project root:
#   pyinstaller build/dita_converter.spec
#
# Output: dist/DITAConverter.exe  (single-file executable)
#
# Session: S-10

import sys
from pathlib import Path
import streamlit
import pdfplumber
import docx as python_docx
import site

# ── Resolve key paths ────────────────────────────────────────────────────────

ROOT           = Path(SPECPATH).parent
STREAMLIT_DIR  = Path(streamlit.__file__).parent
PDFPLUMBER_DIR = Path(pdfplumber.__file__).parent

# Locate site-packages to find dist-info metadata folders
_site = Path(site.getsitepackages()[0])

def _meta(pkg_folder_name: str):
    """Return (src, dest) tuple for a dist-info folder if it exists."""
    candidates = list(_site.glob(f"{pkg_folder_name}-*.dist-info"))
    if candidates:
        d = candidates[0]
        return (str(d), str(Path(".") / d.name))
    return None

# ── Collect data files ───────────────────────────────────────────────────────

added_files = [
    # Application source
    (str(ROOT / "agents"),        "agents"),
    (str(ROOT / "config"),        "config"),
    (str(ROOT / "ui" / "app.py"), "ui"),

    # Streamlit static assets
    (str(STREAMLIT_DIR / "static"),  "streamlit/static"),
    (str(STREAMLIT_DIR / "runtime"), "streamlit/runtime"),

    # pdfplumber data
    (str(PDFPLUMBER_DIR), "pdfplumber"),
]

# Add dist-info metadata for packages that call importlib.metadata internally
for pkg in ["streamlit", "pdfplumber", "python_docx", "PyYAML", "lxml",
            "altair", "numpy", "pandas", "pyarrow", "click", "pillow",
            "Pillow", "packaging", "importlib_metadata"]:
    entry = _meta(pkg)
    if entry:
        added_files.append(entry)

# ── Hidden imports ───────────────────────────────────────────────────────────
# Modules PyInstaller cannot detect through static analysis

hidden = [
    # Streamlit internals
    "streamlit",
    "streamlit.web",
    "streamlit.web.cli",
    "streamlit.runtime",
    "streamlit.runtime.scriptrunner",
    "streamlit.components.v1",

    # App dependencies
    "pdfplumber",
    "pdfminer",
    "pdfminer.high_level",
    "pdfminer.layout",
    "docx",
    "docx.oxml",
    "docx.oxml.ns",
    "yaml",
    "lxml",
    "lxml.etree",
    "lxml._elementpath",

    # Metadata resolution
    "importlib.metadata",
    "importlib_metadata",
    "packaging",
    "packaging.version",
    "packaging.requirements",
    "pyarrow",
    "tornado",
    "click",
    "packaging",
    "importlib_metadata",
    "watchdog",
    "gitpython",
    "validators",
    "toml",
    "tzlocal",
    "cachetools",
]

# ── Analysis ─────────────────────────────────────────────────────────────────

a = Analysis(
    [str(ROOT / "build" / "launcher.py")],   # entry point
    pathex=[str(ROOT)],
    binaries=[],
    datas=added_files,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude heavy unused packages to keep exe smaller
        "matplotlib",
        "scipy",
        "sklearn",
        "tensorflow",
        "torch",
        "IPython",
        "notebook",
        "jupyter",
        "pytest",
        "black",
        "pylint",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# ── Single-file exe ──────────────────────────────────────────────────────────

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="DITAConverter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,                   # compress with UPX if available (reduces size ~30%)
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,               # keep console visible so users can see status messages
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,                  # replace with path to .ico file if you have one
    # version=str(ROOT / "build" / "version_info.txt"),  # uncomment after creating version file
)
