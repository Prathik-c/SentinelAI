# SentinelAI CLI Usage Manual

SentinelAI features a comprehensive Command Line Interface (CLI) to orchestrate, diagnose, configure, and monitor services.

## CLI Execution Syntax

```bash
sentinelai [COMMAND] [OPTIONS]
```

---

## 1. System Orchestration Commands

### `sentinelai start`
Bootstrap and daemonize the entire SentinelAI application stack.
- **Parameters**: 
  - `--no-ui`: Run only the FastAPI server and background monitors (skips launching React frontend).
- **Behavior**:
  1. Checks if Ollama is running (spawns `ollama serve` if offline).
  2. Ensures the configured LLM model exists locally (downloads if missing).
  3. Pre-loads (warms) the model into system VRAM.
  4. Runs pending database schema synchronizations.
  5. Computes/primes the behavioral baseline stats.
  6. Spawns FastAPI backend (`localhost:8000`) and React frontend (`localhost:5173`) in detached processes.
  7. Tracks spawned PIDs in `.sentinel_pids`.

### `sentinelai stop`
Shut down all daemonized processes cleanly.
- **Behavior**:
  1. Reads `.sentinel_pids`.
  2. Terminates Uvicorn and Vite processes including all sub-children recursively.
  3. Commands Ollama to unload the active model to free system VRAM.
  4. Cleans up `.sentinel_pids`.

---

## 2. Diagnostics & Telemetry

### `sentinelai status`
Prints a live summary of all active services, database size, and system resource metrics.
- **Checks**:
  - API backend connection & uptime.
  - SQLite database size and logs count.
  - Live CPU, RAM, Disk percentages.
  - Active VRAM model status.

### `sentinelai doctor`
Exhaustive troubleshooting utility verifying dependencies, system specifications, and installation directories.
- **Checks**:
  - Python version (requires >= 3.10).
  - Port 8000 availability.
  - Disk space availability (> 10GB recommended).
  - RAM capacity (>= 8GB recommended).
  - Installation of package dependencies.

---

## 3. Configuration Management

### `sentinelai config show`
Outputs the active config variables merged from `sentinelai.yaml` and `.env` variables.

### `sentinelai config edit`
Opens `sentinelai.yaml` configuration file in the system default text editor (e.g. Notepad on Windows).

---

## 4. Administrative Utilities

### `sentinelai logs`
Display or follow system log outputs.
- **Log Types**: `application`, `backend`, `llm`, `behavior`, `database`, `startup`
- **Parameters**:
  - `-n`, `--lines N`: Last lines to display (default 30).
  - `-f`, `--follow`: Stream and tail new incoming logs.

### `sentinelai report`
Triggers an immediate weekly system health audit generation.
- **Parameters**:
  - `--days N`: Set audit window size (default 7 days).

### `sentinelai chat`
Interactive local prompt to query your computer's health logs using RAG.
- **Exit**: Type `exit` or `quit` to return to shell.

### `sentinelai warm-model`
Manually warm/pre-load model into VRAM immediately.

### `sentinelai version`
Prints SentinelAI installation version.
