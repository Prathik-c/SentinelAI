import os
import sys
import time
import asyncio
import subprocess
import shutil
import httpx
import yaml
import psutil
from pathlib import Path
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

# Ensure backend folder is in path
from sentinelai_cli.utils import (
    bootstrap_backend,
    save_pids,
    load_pids,
    clear_pids,
    is_pid_running,
    kill_pid_gracefully,
    check_ollama_installed,
    check_ollama_running,
    start_ollama_service,
    ROOT_DIR,
    BACKEND_DIR
)

bootstrap_backend()

app = typer.Typer(
    help="SentinelAI CLI - Manage and monitor local behavioural intelligence",
    no_args_is_help=True
)

console = Console()

# Define config sub-app
config_app = typer.Typer(help="Manage SentinelAI configuration parameters")
app.add_typer(config_app, name="config")

@app.command()
def version():
    """Display application version."""
    console.print("[bold cyan]SentinelAI[/bold cyan] [bold green]v2.0.0[/bold green]")

@app.command()
def stop():
    """Gracefully shut down SentinelAI processes."""
    pids = load_pids()
    if not pids:
        console.print("[yellow]No active SentinelAI processes found running via CLI.[/yellow]")
        # Double check if uvicorn is running anyway
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if "uvicorn" in proc.info['name'].lower() or ("python" in proc.info['name'].lower() and "main.py" in " ".join(proc.cmdline())):
                    console.print(f"[yellow]Found orphaned backend process PID {proc.info['pid']}, terminating...[/yellow]")
                    kill_pid_gracefully(proc.info['pid'])
            except Exception:
                pass
        return

    console.print("[bold yellow]Shutting down SentinelAI...[/bold yellow]")
    
    if "backend" in pids:
        console.print(f"Stopping FastAPI Backend (PID {pids['backend']})...")
        kill_pid_gracefully(pids["backend"])
        
    if "frontend" in pids:
        console.print(f"Stopping React Frontend (PID {pids['frontend']})...")
        kill_pid_gracefully(pids["frontend"])

    # Unload Ollama model from VRAM/RAM
    try:
        import config as backend_config
        base_url = getattr(backend_config, "OLLAMA_BASE_URL", "http://localhost:11434")
        chat_model = getattr(backend_config, "CHAT_MODEL", "mistral:7b")
        # Ollama protocol to unload: keep_alive: 0
        httpx.post(f"{base_url}/api/chat", json={"model": chat_model, "messages": [], "keep_alive": 0}, timeout=2.0)
        console.print("[green]Ollama model resources released.[/green]")
    except Exception:
        pass

    clear_pids()
    console.print("[bold green]All services stopped successfully.[/bold green]")

@app.command("warm-model")
def warm_model_cmd():
    """Pre-load the configured Ollama model into system VRAM/RAM."""
    console.print("[bold yellow]Warming Ollama model into VRAM...[/bold yellow]")
    
    if not check_ollama_running():
        console.print("[bold red]Error: Ollama service is not running. Please start it first.[/bold red]")
        raise typer.Exit(1)
        
    async def run_warmup():
        from services.ollama_client import warm_model
        return await warm_model()
        
    t0 = time.time()
    success = asyncio.run(run_warmup())
    duration = time.time() - t0
    
    if success:
        console.print(f"[bold green]Model warmed up successfully in {duration:.2f}s.[/bold green]")
    else:
        console.print("[bold red]Model warmup failed. Please verify model configuration and Ollama status.[/bold red]")
        raise typer.Exit(1)

@config_app.command("show")
def config_show():
    """Display active merged configuration settings."""
    import config as backend_config
    
    table = Table(title="Active Config (Merged YAML & Env)")
    table.add_column("Category", style="cyan")
    table.add_column("Parameter", style="magenta")
    table.add_column("Value", style="green")
    
    # Group attributes
    attrs = {
        "Ollama": ["OLLAMA_BASE_URL", "CHAT_MODEL", "REPORT_MODEL", "LLM_TIMEOUT_SECONDS", "OLLAMA_KEEP_ALIVE"],
        "Database": ["DB_PATH"],
        "Paths": ["SNAPSHOTS_PATH", "KNOWN_FACES_PATH", "REPORTS_DIR", "LOGS_DIR"],
        "Monitoring": ["HEALTH_INTERVAL", "LOG_INTERVAL"],
        "Behavior": ["MIN_BASELINE_SAMPLES", "KNOWN_PROCESS_THRESHOLD", "CPU_ANOMALY_MULTIPLIER", "RAM_ANOMALY_MARGIN", "MAX_LOG_CONTEXT_ROWS", "BASELINE_CACHE_TTL"],
        "Logging": ["LOG_LEVEL"]
    }
    
    for cat, params in attrs.items():
        for param in params:
            val = getattr(backend_config, param, "Not Defined")
            table.add_row(cat, param, str(val))
            
    console.print(table)

@config_app.command("edit")
def config_edit():
    """Open config file in system editor."""
    yaml_path = ROOT_DIR / "sentinelai.yaml"
    if not yaml_path.exists():
        console.print(f"[yellow]Creating default {yaml_path.name}...[/yellow]")
        # Write default
        default_yaml = """# SentinelAI Config
ollama:
  base_url: "http://localhost:11434"
  chat_model: "mistral:7b"
  report_model: "mistral:7b"
  timeout_seconds: 60
database:
  path: "./data/sentinelai.db"
logging:
  level: "INFO"
  dir: "./logs"
"""
        yaml_path.write_text(default_yaml)
        
    console.print(f"Opening [bold cyan]{yaml_path.resolve()}[/bold cyan] in system editor...")
    
    # Try editor commands based on OS
    if os.name == 'nt':
        os.system(f'notepad.exe "{yaml_path}"')
    else:
        editor = os.environ.get('EDITOR', 'nano')
        subprocess.run([editor, str(yaml_path)])

@app.command()
def chat():
    """Start an interactive chat session with SentinelAI."""
    bootstrap_backend()
    from database import SessionLocal
    from services.rag_service import answer_question
    
    console.print(Panel(
        "[bold green]SentinelAI Behavioural Intelligence Agent CLI[/bold green]\n"
        "Ask questions like: 'Any anomalies today?', 'What processes are running?', 'Is my RAM normal?'\n"
        "Type 'exit' or 'quit' to end the session.",
        title="Interactive RAG Chat"
    ))
    
    db = SessionLocal()
    try:
        while True:
            q = console.input("[bold yellow]You > [/bold yellow]").strip()
            if q.lower() in ("exit", "quit"):
                break
            if not q:
                continue
                
            with console.status("[cyan]SentinelAI is thinking...[/cyan]"):
                ans = asyncio.run(answer_question(db, q))
                
            console.print(f"[bold green]AI > [/bold green]{ans}\n")
    finally:
        db.close()

@app.command()
def report(days: int = typer.Option(7, help="Generate report over last N days")):
    """Force generate weekly system behavior audit report."""
    bootstrap_backend()
    from database import SessionLocal
    from services.report_engine import generate_weekly_report
    
    console.print(f"[yellow]Generating system behavior report for the last {days} days...[/yellow]")
    db = SessionLocal()
    
    try:
        async def run_report():
            return await generate_weekly_report(db, days=days)
            
        res = asyncio.run(run_report())
        console.print("[bold green]✓ Weekly report generated successfully![/bold green]")
        console.print(f"Health Score: [cyan]{res.get('health_score', 'N/A')}[/cyan]")
        console.print(f"Risk Score: [cyan]{res.get('risk_score', 'N/A')}[/cyan]")
    except Exception as e:
        console.print(f"[bold red]Failed to generate report: {e}[/bold red]")
    finally:
        db.close()

@app.command()
def logs(
    type: str = typer.Argument("backend", help="Type of log (application, backend, llm, behavior, database, startup)"),
    lines: int = typer.Option(30, "--lines", "-n", help="Number of last lines to show"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow / tail the logs output")
):
    """View and tail application log files."""
    import config as backend_config
    log_dir = Path(getattr(backend_config, "LOGS_DIR", "./logs"))
    log_file = log_dir / f"{type}.log"
    
    if not log_file.exists():
        console.print(f"[bold red]Log file {log_file} does not exist.[/bold red]")
        raise typer.Exit(1)
        
    console.print(f"[cyan]Displaying last {lines} lines of {log_file.name}...[/cyan]")
    
    def print_last_lines():
        with open(log_file, "r") as f:
            lines_list = f.readlines()
            for line in lines_list[-lines:]:
                print(line, end="")
                
    print_last_lines()
    
    if follow:
        console.print("\n[yellow]Tailing logs (Press Ctrl+C to stop)...[/yellow]")
        try:
            with open(log_file, "r") as f:
                f.seek(0, os.SEEK_END)
                while True:
                    line = f.readline()
                    if not line:
                        time.sleep(0.1)
                        continue
                    print(line, end="")
        except KeyboardInterrupt:
            pass

@app.command()
def start(no_ui: bool = typer.Option(False, "--no-ui", help="Do not launch React frontend UI")):
    """Start the SentinelAI service suite."""
    from sentinelai_cli.commands.start import run_start
    run_start(no_ui=no_ui)

@app.command()
def doctor():
    """Verify system requirements and SentinelAI dependencies."""
    from sentinelai_cli.commands.doctor import run_doctor
    success = run_doctor()
    if not success:
        raise typer.Exit(1)

@app.command()
def status():
    """Display real-time status of SentinelAI services and resources."""
    from sentinelai_cli.commands.status import run_status
    run_status()
