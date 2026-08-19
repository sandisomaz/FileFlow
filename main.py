import sys
import ctypes
import threading
import socket
import time
import uvicorn
try:
    import webview
except ImportError:
    webview = None
import os
import logging
import multiprocessing
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# ── Windows multiprocessing guard ──────────────────────────────────────────────
# MUST be called before anything else on Windows when using multiprocessing.Pool
# inside a frozen (PyInstaller) executable. Without this, child processes
# re-execute main.py and crash on startup.
if __name__ == "__main__":
    multiprocessing.freeze_support()

# Establish App Root
APP_ROOT = Path(__file__).parent
sys.path.append(str(APP_ROOT))

from app.api import FileFlowAPI

app = FastAPI()
def find_available_port(host: str = "127.0.0.1", start_port: int = 4173, max_attempts: int = 50) -> int:
    """Finds the first available TCP port to prevent startup crashes from port collisions."""
    for p in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, p))
                return p
            except OSError:
                continue
    return start_port

SERVER_HOST = "127.0.0.1"
SERVER_PORT = find_available_port(SERVER_HOST, 4173)

# Restrict CORS to the actual local host and port
app.add_middleware(
    CORSMiddleware,
    allow_origins=[f"http://{SERVER_HOST}:{SERVER_PORT}"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

UI_DIR    = APP_ROOT / "ui"
ASSETS_DIR = APP_ROOT / "assets"
ICON_PATH  = ASSETS_DIR / "logo.ico"

if UI_DIR.exists():
    app.mount("/", StaticFiles(directory=str(UI_DIR), html=True), name="ui")

def run_background_api():
    """Runs the FastAPI / static-asset server in a daemon thread."""
    config = uvicorn.Config(app, host=SERVER_HOST, port=SERVER_PORT, log_level="error")
    server = uvicorn.Server(config)
    server.run()


def wait_for_server(host: str = SERVER_HOST, port: int = SERVER_PORT, timeout: int = 15) -> bool:
    """
    Blocks until the FastAPI server is accepting connections, or until timeout.
    Prevents the pywebview window from loading before the server is ready,
    which caused a blank / error page on slow machines.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.1)
    logging.warning(f"[Launch] Server did not become ready within {timeout}s")
    return False


def create_desktop_shortcut():
    """Creates a Windows Desktop Shortcut for the app (silent, best-effort)."""
    if os.name != "nt":
        return
    try:
        desktop = Path(os.environ["USERPROFILE"]) / "Desktop"
        shortcut_path = desktop / "FileFlow.lnk"
        if shortcut_path.exists():
            return

        import subprocess
        pythonw = Path(sys.executable).parent / "pythonw.exe"
        if not pythonw.exists():
            pythonw = "pythonw.exe"

        ps_script = f"""
        $WshShell = New-Object -ComObject WScript.Shell
        $Shortcut = $WshShell.CreateShortcut('{shortcut_path}')
        $Shortcut.TargetPath = '{pythonw}'
        $Shortcut.Arguments = '"{APP_ROOT / "main.py"}"'
        $Shortcut.WorkingDirectory = '"{APP_ROOT}"'
        $Shortcut.IconLocation = '"{ICON_PATH}"'
        $Shortcut.Description = 'FileFlow — Your Personal Digital Associate'
        $Shortcut.Save()
        """
        subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
    except Exception:
        pass  # Never crash on shortcut creation


def launch():
    """Main launch sequence."""
    # ── 0. Windows taskbar branding ────────────────────────────────────────────
    if os.name == "nt":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "com.fileflow.app.v10"
            )
        except Exception:
            pass

    # ── 0.1 Desktop shortcut ───────────────────────────────────────────────────
    create_desktop_shortcut()

    # ── 1. Logging & data dir ──────────────────────────────────────────────────
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    Path(APP_ROOT / "data").mkdir(exist_ok=True)

    # ── 2. Start asset server in background ────────────────────────────────────
    t = threading.Thread(target=run_background_api, daemon=True)
    t.start()

    # ── 3. Wait until server is ready BEFORE creating the window ───────────────
    # This fixes the blank-page race condition on startup.
    logging.info("[Launch] Waiting for asset server…")
    if not wait_for_server():
        logging.error("[Launch] Asset server failed to start. Exiting.")
        sys.exit(1)
    logging.info("[Launch] Server ready. Opening window.")

    # ── 4. Create API bridge (needs window ref — set after window creation) ─────
    api_bridge = FileFlowAPI(None)

    # ── 5. Create window ───────────────────────────────────────────────────────
    window = webview.create_window(
        title="FileFlow",
        url=f"http://{SERVER_HOST}:{SERVER_PORT}/",
        width=1340,
        height=860,
        background_color="#ffffff",
        text_select=True,
        maximized=True,
        frameless=False,
        resizable=True,
        js_api=api_bridge,
    )

    # Give the API its real window reference
    api_bridge._window = window

    # ── 6. Start UI ────────────────────────────────────────────────────────────
    final_icon = str(ICON_PATH.resolve()) if ICON_PATH.exists() else None
    webview.start(debug=False, icon=final_icon)


if __name__ == "__main__":
    launch()