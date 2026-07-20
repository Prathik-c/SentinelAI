import os
import psutil
import httpx
import time
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

def run_status():
    """Print active status of all SentinelAI services and resources."""
    import config as backend_config
    
    db_path = Path(backend_config.DB_PATH)
    ollama_url = backend_config.OLLAMA_BASE_URL
    chat_model = backend_config.CHAT_MODEL
    
    # 1. API Backend Status
    backend_ok = False
    backend_uptime = "N/A"
    try:
        resp = httpx.get("http://localhost:8000/ping", timeout=1.0)
        if resp.status_code == 200:
            backend_ok = True
            # Use generic uptime based on system boot (already calculated later)
            backend_uptime = "Active"
    except Exception:
        pass
        
    backend_status_str = "[green]ONLINE[/green]" if backend_ok else "[red]OFFLINE[/red]"
    
    # 2. Database stats
    db_exists = db_path.exists()
    db_size_mb = (db_path.stat().st_size / (1024 * 1024)) if db_exists else 0.0
    logs_count = 0
    incidents_count = 0
    
    if db_exists:
        try:
            from database import SessionLocal
            from models.tables import HealthLog, Incident
            db = SessionLocal()
            logs_count = db.query(HealthLog).count()
            incidents_count = db.query(Incident).count()
            db.close()
            db_status_str = "[green]OK (Connection Succeeded)[/green]"
        except Exception as e:
            db_status_str = f"[red]ERROR (Connection Failed: {e})[/red]"
    else:
        db_status_str = "[yellow]WARN (Missing - Will create on start)[/yellow]"

    # 3. CPU/RAM/Disk stats
    cpu_percent = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage('.')
    
    # 4. Ollama Model status
    model_loaded = False
    try:
        resp = httpx.get(f"{ollama_url}/api/ps", timeout=1.5)
        if resp.status_code == 200:
            loaded_models = resp.json().get("models", [])
            for m in loaded_models:
                if chat_model in m.get("name", ""):
                    model_loaded = True
                    break
    except Exception:
        pass
        
    model_loaded_str = "[green]LOADED (in memory)[/green]" if model_loaded else "[yellow]UNLOADED (cold)[/yellow]"
    
    # 5. Background Engine & Logger Status
    # We can infer background engine is running if backend is running.
    engine_status_str = "[green]ACTIVE[/green]" if backend_ok else "[red]INACTIVE[/red]"
    logger_status_str = "[green]ACTIVE[/green]" if backend_ok else "[red]INACTIVE[/red]"
    
    # 6. Boot / Uptime
    boot_time = psutil.boot_time()
    system_uptime_seconds = time.time() - boot_time
    uptime_hours = system_uptime_seconds // 3600
    uptime_mins = (system_uptime_seconds % 3600) // 60
    
    # Display table
    table = Table(show_header=False, box=None)
    table.add_row("[bold cyan]Backend API[/bold cyan]", backend_status_str)
    table.add_row("  Uptime", str(backend_uptime))
    table.add_row("[bold cyan]Database[/bold cyan]", db_status_str)
    table.add_row("  File Path", str(db_path.resolve()))
    table.add_row("  File Size", f"{db_size_mb:.2f} MB")
    table.add_row("  Total Logs", str(logs_count))
    table.add_row("  Total Incidents", str(incidents_count))
    table.add_row("[bold cyan]System Resources[/bold cyan]", f"CPU: {cpu_percent}% | RAM: {ram.percent}% | Disk: {disk.percent}%")
    table.add_row("  System Uptime", f"{int(uptime_hours)}h {int(uptime_mins)}m")
    table.add_row("[bold cyan]Background Logger[/bold cyan]", logger_status_str)
    table.add_row("[bold cyan]Behavior Engine[/bold cyan]", engine_status_str)
    table.add_row("[bold cyan]Ollama Model[/bold cyan]", f"'{chat_model}'")
    table.add_row("  VRAM Status", model_loaded_str)
    
    console.print(Panel(table, title="SentinelAI Live Status Summary", border_style="cyan"))
