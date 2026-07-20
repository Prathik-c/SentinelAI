import os
import sys
import psutil
import shutil
import httpx
import socket
from pathlib import Path
from rich.console import Console
from rich.table import Table

console = Console()

def run_doctor():
    """Verify all system requirements for SentinelAI."""
    console.print("[bold yellow]Running SentinelAI Doctor diagnostics...[/bold yellow]\n")
    
    table = Table(title="Diagnostic Checks")
    table.add_column("Resource/Dependency", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Details", style="magenta")
    
    has_fail = False
    
    # 1. Python Version
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 10):
        table.add_row("Python Version", "[green]OK[/green]", f"Version {py_ver}")
    else:
        table.add_row("Python Version", "[red]FAIL[/red]", f"Version {py_ver} (Requires >= 3.10)")
        has_fail = True
        
    # Import backend config to retrieve DB path and log dir
    try:
        import config as backend_config
        db_path = Path(backend_config.DB_PATH)
        logs_dir = Path(backend_config.LOGS_DIR)
        chat_model = backend_config.CHAT_MODEL
        ollama_url = backend_config.OLLAMA_BASE_URL
        web_port = 8000
    except Exception as e:
        table.add_row("Config loading", "[red]FAIL[/red]", f"Failed to import config: {e}")
        console.print(table)
        return False
        
    # 2. Required Folders
    folders = [
        db_path.parent,
        logs_dir,
        Path(backend_config.SNAPSHOTS_PATH),
        Path(backend_config.KNOWN_FACES_PATH)
    ]
    missing_folders = [str(f) for f in folders if not f.exists()]
    if not missing_folders:
        table.add_row("Required Folders", "[green]OK[/green]", "All storage directories exist")
    else:
        table.add_row("Required Folders", "[yellow]WARN[/yellow]", f"Missing: {', '.join(missing_folders)} (will create at start)")
        
    # 3. SQLite Database
    if db_path.exists():
        table.add_row("SQLite DB File", "[green]OK[/green]", f"Database exists at {db_path}")
    else:
        table.add_row("SQLite DB File", "[yellow]WARN[/yellow]", f"Database file does not exist yet (will create at start)")
        
    # 4. Database Schema
    try:
        from database import engine
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        table.add_row("DB Schema / Connection", "[green]OK[/green]", "Database connection succeeded")
    except Exception as e:
        table.add_row("DB Schema / Connection", "[red]FAIL[/red]", f"Failed to connect to database: {e}")
        has_fail = True

    # 5. Ollama Installed
    ollama_path = shutil.which("ollama")
    if ollama_path:
        table.add_row("Ollama Installed", "[green]OK[/green]", f"Ollama executable found in PATH")
    else:
        table.add_row("Ollama Installed", "[red]FAIL[/red]", "Ollama not found. Install it from https://ollama.com")
        has_fail = True

    # 6. Ollama Daemon Running
    ollama_running = False
    try:
        resp = httpx.get(f"{ollama_url}/api/tags", timeout=2.0)
        if resp.status_code == 200:
            ollama_running = True
            table.add_row("Ollama Daemon", "[green]OK[/green]", f"Running and reachable on {ollama_url}")
        else:
            table.add_row("Ollama Daemon", "[red]FAIL[/red]", f"Unusual status code {resp.status_code} from {ollama_url}")
            has_fail = True
    except Exception as e:
        table.add_row("Ollama Daemon", "[red]FAIL[/red]", f"Not reachable on {ollama_url}. Run 'ollama serve' or check service status.")
        has_fail = True

    # 7. Required LLM Model
    if ollama_running:
        try:
            models_data = resp.json().get("models", [])
            model_names = [m.get("name") for m in models_data]
            matched = any(chat_model in name for name in model_names)
            if matched:
                table.add_row("Required Model", "[green]OK[/green]", f"Model '{chat_model}' exists locally")
            else:
                table.add_row("Required Model", "[red]FAIL[/red]", f"Model '{chat_model}' not pulled. Run 'ollama pull {chat_model}'")
                has_fail = True
        except Exception as e:
            table.add_row("Required Model", "[red]FAIL[/red]", f"Failed parsing models list: {e}")
            has_fail = True
    else:
        table.add_row("Required Model", "[yellow]WARN[/yellow]", f"Unable to check model (Ollama offline)")

    # 8. FastAPI Port Availability
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", web_port))
        table.add_row("Port Availability", "[green]OK[/green]", f"Port {web_port} is available")
    except socket.error:
        table.add_row("Port Availability", "[yellow]WARN[/yellow]", f"Port {web_port} is currently in use (FastAPI may already be running)")
    finally:
        s.close()

    # 9. Frontend Build & Node Packages
    from sentinelai_cli.utils import ROOT_DIR
    frontend_dir = ROOT_DIR / "frontend"
    if (frontend_dir / "package.json").exists():
        if (frontend_dir / "node_modules").exists():
            table.add_row("Frontend Directory", "[green]OK[/green]", "Vite frontend files and node_modules exist")
        else:
            table.add_row("Frontend Directory", "[yellow]WARN[/yellow]", "node_modules missing in frontend. Run npm install.")
    else:
        table.add_row("Frontend Directory", "[red]FAIL[/red]", "Frontend folder not found at project root")
        has_fail = True

    # 10. System Specs
    cores = psutil.cpu_count(logical=True)
    table.add_row("CPU Support", "[green]OK[/green]", f"{cores} logical CPU cores detected")
    
    mem = psutil.virtual_memory()
    total_gb = mem.total / (1024**3)
    free_gb = mem.available / (1024**3)
    if total_gb >= 8:
        table.add_row("System Memory", "[green]OK[/green]", f"Total: {total_gb:.1f} GB (Available: {free_gb:.1f} GB)")
    else:
        table.add_row("System Memory", "[yellow]WARN[/yellow]", f"Total: {total_gb:.1f} GB (Requires >= 8 GB for stable LLM inference)")

    disk = psutil.disk_usage('.')
    free_disk_gb = disk.free / (1024**3)
    if free_disk_gb >= 10:
        table.add_row("Disk Space", "[green]OK[/green]", f"{free_disk_gb:.1f} GB free space on drive")
    else:
        table.add_row("Disk Space", "[red]FAIL[/red]", f"Only {free_disk_gb:.1f} GB free space (requires >= 10 GB)")
        has_fail = True

    # 11. Required Python Packages Check
    packages = ["fastapi", "uvicorn", "sqlalchemy", "loguru", "typer", "rich", "yaml", "psutil", "pynput"]
    missing_packages = []
    for pkg in packages:
        try:
            __import__(pkg)
        except ImportError:
            missing_packages.append(pkg)
            
    if not missing_packages:
        table.add_row("Required Packages", "[green]OK[/green]", "All required Python libraries are installed")
    else:
        table.add_row("Required Packages", "[red]FAIL[/red]", f"Missing libraries: {', '.join(missing_packages)}")
        has_fail = True

    console.print(table)
    return not has_fail
