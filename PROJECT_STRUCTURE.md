# SentinelAI Project Structure Directory

This document details the code layout and responsibilities of each directory and file in SentinelAI.

---

## Directory Map

```text
SentinelAI/
├── .env                          # Local overrides for security / paths
├── pyproject.toml                # Project packaging setup & console scripts
├── sentinelai.yaml               # Default system configuration parameters
├── ARCHITECTURE.md               # Core mechanics and sequence flows
├── CLI_USAGE.md                  # CLI command specifications
├── DEPLOYMENT.md                 # Local setup & compiling procedures
├── PROJECT_STRUCTURE.md          # File directory roadmap [This file]
│
├── backend/                      # FastAPI Backend Engine
│   ├── main.py                   # FastAPI Application initialization
│   ├── config.py                 # Configuration validation & loader
│   ├── database.py               # SQLite Session & Engine setup
│   ├── core/                     # Logging configuration & db migrator
│   ├── models/                   # DB schemas & database table maps
│   ├── routers/                  # API endpoints (alerts, system, reports, chat)
│   ├── services/                 # Business logic
│   │   ├── analyzers/            # Behavior anomaly evaluation engines
│   │   ├── activity_service.py   # Telemetry logger for mouse/keyboard idle states
│   │   ├── anomaly_engine.py     # Main scheduler orchestration loop
│   │   ├── baseline_engine.py    # Compute average metrics and baseline stats
│   │   ├── incident_engine.py    # Create alerts & catalog anomalies
│   │   ├── ollama_client.py      # Connection pooled client wrapper for Ollama
│   │   ├── rag_service.py        # Question categorization & dynamic time fetchers
│   │   └── scheduler.py          # Background worker triggers
│   └── utils/                    # PDF generator & prompt blueprints
│
├── frontend/                     # React UI (Vite dev server)
│   ├── package.json              # NPM script controls & UI dependencies
│   ├── vite.config.js            # Build options & proxy configs
│   ├── src/
│   │   ├── main.jsx              # UI React root mount
│   │   ├── App.jsx               # UI Shell & Tab orchestration
│   │   ├── components/           # Panels for Alerts, Chat, Reports, & System Stats
│   │   └── hooks/                # WebSocket state controllers
│
└── sentinelai_cli/               # Typer CLI Control Suite
    ├── __init__.py
    ├── main.py                   # Command router (start, stop, logs, report, etc.)
    ├── utils.py                  # Daemon helpers, PID tracking & path wrappers
    └── commands/                 # Executable orchestration scripts
        ├── doctor.py             # Doctor verification procedures
        ├── start.py              # CLI bootstrap & timing benchmarks
        └── status.py             # Telemetry inspection & API ping checks
```

---

## Key File Descriptions

- **`pyproject.toml`**: Instructs `pip` on how to install SentinelAI as a package, specifying required packages and registering the `sentinelai` console script so it can be called from any command prompt.
- **`sentinelai.yaml`**: The primary declarative configuration. Values here are read on start and can be overridden by environment variables in `.env`.
- **`backend/core/logging_config.py`**: Intercepts FastAPI, Uvicorn, and SentinelAI telemetry, automatically routing logs into 6 dedicated rotating log files.
- **`sentinelai_cli/utils.py`**: Contains helper methods for checking Ollama, executing background shell tasks on Windows, and tracking running process IDs in `.sentinel_pids`.
