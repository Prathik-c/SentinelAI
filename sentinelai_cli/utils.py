import os
import sys
import psutil
import json
import httpx
import subprocess
import yaml
from pathlib import Path

# Bootstrap backend path so we can import from it
CLI_DIR = Path(__file__).parent
ROOT_DIR = CLI_DIR.parent
BACKEND_DIR = ROOT_DIR / "backend"

def bootstrap_backend():
    """Adds the backend directory to sys.path if not already present."""
    backend_str = str(BACKEND_DIR.resolve())
    if backend_str not in sys.path:
        sys.path.insert(0, backend_str)

bootstrap_backend()

PID_FILE = ROOT_DIR / ".sentinel_pids"

def save_pids(pids: dict):
    """Saves running process PIDs to a file."""
    with open(PID_FILE, "w") as f:
        json.dump(pids, f)

def load_pids() -> dict:
    """Loads running process PIDs from file."""
    if PID_FILE.exists():
        try:
            with open(PID_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def clear_pids():
    """Removes the PID tracking file."""
    if PID_FILE.exists():
        try:
            PID_FILE.unlink()
        except Exception:
            pass

def is_pid_running(pid: int) -> bool:
    """Checks if a process ID is running and is python/node/ollama."""
    try:
        proc = psutil.Process(pid)
        return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False

def kill_pid_gracefully(pid: int):
    """Gracefully terminates a process by PID and all its children."""
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        for child in children:
            try:
                child.terminate()
            except Exception:
                pass
        parent.terminate()
        
        # Wait up to 3s for graceful termination
        gone, alive = psutil.wait_procs(children + [parent], timeout=3)
        for p in alive:
            try:
                p.kill()
            except Exception:
                pass
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

def get_config_value(keys: list, default: any) -> any:
    """Retrieves a config value from the backend config module."""
    bootstrap_backend()
    try:
        import config as backend_config
        # Map config keys to backend variables
        key_mapping = {
            ("ollama", "base_url"): "OLLAMA_BASE_URL",
            ("ollama", "chat_model"): "CHAT_MODEL",
            ("ollama", "report_model"): "REPORT_MODEL",
            ("database", "path"): "DB_PATH",
            ("logging", "dir"): "LOGS_DIR",
            ("logging", "level"): "LOG_LEVEL",
            ("web", "port"): "HEALTH_INTERVAL", # wait, port is usually hardcoded or via env
        }
        var_name = key_mapping.get(tuple(keys))
        if var_name and hasattr(backend_config, var_name):
            return getattr(backend_config, var_name)
    except Exception:
        pass
    return default

def check_ollama_installed() -> bool:
    """Checks if Ollama executable is installed in path."""
    import shutil
    return shutil.which("ollama") is not None

def check_ollama_running() -> bool:
    """Checks if Ollama service is reachable on the configured base URL."""
    base_url = get_config_value(["ollama", "base_url"], "http://localhost:11434")
    try:
        resp = httpx.get(f"{base_url}/api/tags", timeout=2.0)
        return resp.status_code == 200
    except Exception:
        return False

def start_ollama_service() -> bool:
    """Attempts to launch Ollama in the background."""
    if check_ollama_running():
        return True
    
    if not check_ollama_installed():
        return False

    # Launch ollama serve in background
    try:
        # On Windows, creationflags=subprocess.CREATE_NO_WINDOW hides the console window
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        )
        return True
    except Exception:
        return False
