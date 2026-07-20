import os
import sys
import time
import asyncio
import subprocess
import httpx
import socket
from pathlib import Path
import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from sentinelai_cli.utils import (
    bootstrap_backend,
    save_pids,
    load_pids,
    is_pid_running,
    check_ollama_running,
    start_ollama_service,
    ROOT_DIR,
    BACKEND_DIR
)

console = Console()

async def warm_ollama_model(base_url: str, model_name: str):
    """Hits /api/chat with empty request and keep_alive to load model into VRAM."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            await client.post(
                f"{base_url}/api/chat",
                json={
                    "model": model_name,
                    "messages": [{"role": "user", "content": "ping"}],
                    "options": {"num_predict": 1},
                    "keep_alive": "24h"
                }
            )
            return True
    except Exception:
        return False

def run_start(no_ui: bool = False):
    """Bootstrap and launch SentinelAI services and daemons."""
    bootstrap_backend()
    
    # Check if already running
    pids = load_pids()
    backend_running = False
    if "backend" in pids and is_pid_running(pids["backend"]):
        backend_running = True
        
    if backend_running:
        console.print("[bold yellow]SentinelAI backend is already running.[/bold yellow]")
        if not no_ui and ("frontend" in pids and is_pid_running(pids["frontend"])):
            console.print("[bold yellow]SentinelAI frontend is also running.[/bold yellow]")
        console.print("Run 'sentinelai stop' to stop running instances.")
        return

    console.print("[bold cyan]Starting SentinelAI System Behavioural Engine...[/bold cyan]\n")
    
    t_start = time.time()
    
    # 1. Database sync
    t0 = time.time()
    try:
        from database import engine, Base, SessionLocal
        from models import tables # noqa: F401
        from core.migrator import sync_schema
        
        # Ensure database directory exists
        db_path = Path(engine.url.database)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        sync_schema(engine, Base.metadata)
        db_time_ms = int((time.time() - t0) * 1000)
        console.print(f"Database........[green]OK[/green] ({db_time_ms} ms)")
    except Exception as e:
        console.print(f"Database........[red]FAILED[/red] ({e})")
        raise typer.Exit(1)

    # 2. Ollama setup
    t0 = time.time()
    import config as backend_config
    ollama_url = backend_config.OLLAMA_BASE_URL
    chat_model = backend_config.CHAT_MODEL
    
    # Ensure service is running
    service_ok = start_ollama_service()
    if not service_ok:
        console.print("Ollama..........[red]FAILED[/red] (Ollama executable not found or failed to start)")
        raise typer.Exit(1)
        
    # Poll until ready
    ollama_ready = False
    for _ in range(20):
        if check_ollama_running():
            ollama_ready = True
            break
        time.sleep(0.5)
        
    if not ollama_ready:
        console.print("Ollama..........[red]FAILED[/red] (Service not responding)")
        raise typer.Exit(1)

    # Check model and pull if missing
    try:
        resp = httpx.get(f"{ollama_url}/api/tags", timeout=2.0)
        models_data = resp.json().get("models", [])
        model_names = [m.get("name") for m in models_data]
        if not any(chat_model in name for name in model_names):
            console.print(f"[yellow]Model '{chat_model}' not found. Downloading model from Ollama library...[/yellow]")
            # Pull model
            subprocess.run(["ollama", "pull", chat_model])
    except Exception as e:
        console.print(f"Ollama..........[red]FAILED[/red] (Error checking models: {e})")
        raise typer.Exit(1)

    # Warm model
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    warmed = loop.run_until_complete(warm_ollama_model(ollama_url, chat_model))
    if not warmed:
        console.print("Ollama..........[yellow]WARNING[/yellow] (Model warmup failed, first query may load slowly)")
        
    ollama_time_s = time.time() - t0
    console.print(f"Ollama..........[green]OK[/green] ({ollama_time_s:.1f} s)")

    # 3. Behavior Engine baseline initialization
    t0 = time.time()
    try:
        from services.baseline_engine import compute_baseline
        db = SessionLocal()
        try:
            # Prime psutil first
            import psutil
            psutil.cpu_percent(interval=0.1)
            # Compute baseline
            compute_baseline(db)
        except Exception:
            # Might throw BaselineNotReadyError which is expected for fresh db
            pass
        finally:
            db.close()
        behavior_time_ms = int((time.time() - t0) * 1000)
        console.print(f"Behavior Engine.[green]OK[/green] ({behavior_time_ms} ms)")
    except Exception as e:
        console.print(f"Behavior Engine.[yellow]WARNING[/yellow] (Failed to precompute baseline: {e})")

    # 4. Launch backend process
    # Create logs directory if missing
    logs_dir = Path(backend_config.LOGS_DIR)
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    backend_log = open(logs_dir / "backend.log", "a")
    
    env = os.environ.copy()
    # Inject python path
    env["PYTHONPATH"] = str(BACKEND_DIR.resolve())
    
    backend_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=str(BACKEND_DIR.resolve()),
        stdout=backend_log,
        stderr=backend_log,
        env=env,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
    )
    
    # Poll backend until it responds
    backend_up = False
    for _ in range(20):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                s.connect(("127.0.0.1", 8000))
                backend_up = True
                break
        except Exception:
            time.sleep(0.5)
            
    if not backend_up:
        console.print("API.............[red]FAILED[/red] (Backend uvicorn process failed to bind port 8000)")
        backend_proc.kill()
        raise typer.Exit(1)
        
    console.print("API.............[green]OK[/green]")
    
    pids = {"backend": backend_proc.pid}

    # 5. Launch React UI optionally
    if not no_ui:
        frontend_dir = ROOT_DIR / "frontend"
        if (frontend_dir / "package.json").exists():
            console.print("Launching React frontend interface...")
            # Run npm run dev in background
            frontend_log = open(logs_dir / "frontend_process.log", "a")
            try:
                # Use shell=True for npm command resolution
                frontend_proc = subprocess.Popen(
                    ["npm", "run", "dev"],
                    cwd=str(frontend_dir.resolve()),
                    stdout=frontend_log,
                    stderr=frontend_log,
                    shell=True
                )
                pids["frontend"] = frontend_proc.pid
                console.print("Frontend UI.....[green]OK[/green] (Vite Dev Server started)")
            except Exception as e:
                console.print(f"Frontend UI.....[yellow]FAILED to start[/yellow] ({e})")
        else:
            console.print("Frontend UI.....[yellow]SKIPPED[/yellow] (package.json not found)")

    # Save PIDs
    save_pids(pids)
    
    duration = time.time() - t_start
    console.print(f"\n[bold green]Ready in {duration:.1f} s[/bold green]")
    if not no_ui:
        console.print("SentinelAI dashboard is running at http://localhost:5173")
        console.print("API Documentation is available at http://localhost:8000/docs")
