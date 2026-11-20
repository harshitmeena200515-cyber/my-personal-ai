"""
Desktop Application Launcher for MY PERSONAL AI.
Launches the FastAPI backend and opens the standalone desktop app window.
"""

import os
import sys
import time
import subprocess
import urllib.request
import webbrowser
from pathlib import Path

ROOT_DIR = Path(__file__).parent.resolve()
VENV_PYTHON = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
PYTHON_EXE = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
SERVER_URL = "http://127.0.0.1:8000"


def is_server_running() -> bool:
    """Check if server is already responding."""
    try:
        with urllib.request.urlopen(f"{SERVER_URL}/health", timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def main():
    print("=" * 60)
    print("🚀 Launching MY PERSONAL AI Desktop Platform")
    print("=" * 60)

    # 1. Start server if not running
    if not is_server_running():
        print("[*] Starting local AI server daemon...")
        server_cmd = [
            PYTHON_EXE,
            "-m",
            "uvicorn",
            "server:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ]
        # Start detached in background
        subprocess.Popen(
            server_cmd,
            cwd=str(ROOT_DIR),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
        )

        # Wait for server ready
        for attempt in range(1, 15):
            time.sleep(0.8)
            if is_server_running():
                print("✅ Server is online and healthy!")
                break
            print(f"[*] Waiting for server startup (attempt {attempt}/15)...")
    else:
        print("✅ Server is already running!")

    # 2. Launch in native Windows App window mode (Edge standalone app)
    app_opened = False
    edge_paths = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
    ]

    for edge_exe in edge_paths:
        if os.path.exists(edge_exe):
            print("[*] Launching standalone desktop application window...")
            subprocess.Popen([
                edge_exe,
                f"--app={SERVER_URL}",
                "--window-size=1280,850",
            ])
            app_opened = True
            break

    # Fallback to default browser if Edge executable path not found
    if not app_opened:
        print("[*] Opening application in default browser...")
        webbrowser.open(SERVER_URL)

    print("\n" + "=" * 60)
    print("✨ MY PERSONAL AI is running successfully!")
    print(f"📍 Local Endpoint: {SERVER_URL}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
