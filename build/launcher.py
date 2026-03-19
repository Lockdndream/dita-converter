"""
build/launcher.py
DITA Converter Tool — Windows Executable Launcher

Session: S-10e

Root cause of 404: Streamlit 1.35 caches config at module import time.
Env vars set before bootstrap.run() are too late — the static file server
path is already locked in.

Fix: Import streamlit._config / streamlit.config first, call set_option()
directly to override the cached values, THEN call bootstrap.run().
"""

import os
import sys
import time
import socket
import threading
import webbrowser
import urllib.request
from pathlib import Path


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).parent.parent

APP_PY = BASE_DIR / "ui" / "app.py"
PORT   = 8501
URL    = f"http://localhost:{PORT}"

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


# ---------------------------------------------------------------------------
# Patch importlib.metadata FIRST — before any streamlit import
# ---------------------------------------------------------------------------

import importlib.metadata as _meta

_real_version = _meta.version

def _patched_version(pkg: str) -> str:
    _KNOWN = {
        "streamlit":   "1.35.0",
        "pdfplumber":  "0.10.4",
        "python-docx": "1.1.2",
        "PyYAML":      "6.0.2",
        "lxml":        "5.3.1",
    }
    return _KNOWN.get(pkg) or _real_version(pkg)

_meta.version = _patched_version

try:
    _real_pkgs = _meta.packages_distributions
    def _safe_pkgs():
        try:
            return _real_pkgs()
        except Exception:
            return {}
    _meta.packages_distributions = _safe_pkgs
except AttributeError:
    pass


# ---------------------------------------------------------------------------
# Patch signal — Streamlit sets SIGTERM which fails on daemon threads
# ---------------------------------------------------------------------------

import signal as _signal_mod

_real_signal = _signal_mod.signal

def _safe_signal(signum, handler):
    try:
        return _real_signal(signum, handler)
    except (ValueError, OSError):
        pass  # "signal only works in main thread" — safe to ignore

_signal_mod.signal = _safe_signal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0


def _wait_for_server(timeout: int = 90) -> bool:
    """Poll /_stcore/health until 200 or timeout."""
    health   = f"http://localhost:{PORT}/_stcore/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(health, timeout=1) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.5)
        print(".", end="", flush=True)
    return False


# ---------------------------------------------------------------------------
# Force Streamlit config overrides after import
# ---------------------------------------------------------------------------

def _force_streamlit_config():
    """
    Override Streamlit config after import via set_option().
    Only set options that are safe for a local desktop deployment.
    Do NOT touch enableCORS or enableXsrfProtection — these interact
    with Streamlit session init internals and cause type errors.
    """
    from streamlit import config as _st_config

    safe_overrides = {
        "server.port":                       PORT,
        "server.headless":                   True,
        "server.fileWatcherType":            "none",
        "browser.gatherUsageStats":          False,
        "global.developmentMode":            False,
        "global.suppressDeprecationWarnings": True,
    }

    for key, val in safe_overrides.items():
        try:
            _st_config.set_option(key, val)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Run server
# ---------------------------------------------------------------------------

def _run_server():
    sys.argv = ["streamlit"]

    # Force config overrides NOW — after streamlit is importable but before
    # the server event loop starts
    _force_streamlit_config()

    try:
        from streamlit.web.bootstrap import run as st_run
        # Signature: run(main_script_path, command_line, args, flag_options)
        # command_line is stored as _script_data.is_hello — must be False (bool)
        # not "" (empty string) which causes protobuf TypeError
        st_run(str(APP_PY), False, [], {})
    except TypeError:
        # Older signature: run(main_script_path, command_line, args)
        from streamlit.web.bootstrap import run as st_run
        st_run(str(APP_PY), False, [])
    except SystemExit:
        pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 50)
    print("  DITA Converter Tool")
    print("  Starting -- please wait...")
    print("=" * 50)

    if _port_in_use(PORT):
        print(f"\nPort {PORT} already in use -- opening existing session.")
        webbrowser.open(URL)
        return

    # Belt-and-suspenders env vars (set before thread starts)
    os.environ["STREAMLIT_SERVER_PORT"]                = str(PORT)
    os.environ["STREAMLIT_SERVER_HEADLESS"]            = "true"
    os.environ["STREAMLIT_SERVER_FILE_WATCHER_TYPE"]   = "none"
    os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    os.environ["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"]    = "false"

    print(f"\nLaunching from: {APP_PY}")
    print("Waiting for server", end="", flush=True)

    t = threading.Thread(target=_run_server, daemon=True)
    t.start()

    # Give the thread a moment to call _force_streamlit_config before polling
    time.sleep(1)

    ready = _wait_for_server(timeout=90)

    if ready:
        print(f"\n\nReady!  Opening {URL}\n")
        webbrowser.open(URL)
        print("Close this window to stop the DITA Converter.\n")
        try:
            t.join()
        except KeyboardInterrupt:
            print("\nStopped.")
    else:
        print(f"\n\nServer did not respond on port {PORT} after 90 seconds.")
        print("Check that nothing else is using port 8501.")
        input("\nPress Enter to exit...")
        sys.exit(1)


if __name__ == "__main__":
    main()
