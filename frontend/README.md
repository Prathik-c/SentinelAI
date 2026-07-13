# SentinelAI 🛡️
**Privacy-first local AI security and system monitoring**

> Runs 100% on your machine. No cloud. No API costs. 
> No data ever leaves your device.

![Python](https://img.shields.io/badge/Python-3.11-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-green)
![React](https://img.shields.io/badge/React-18-61dafb)
![Ollama](https://img.shields.io/badge/LLM-Qwen3:8b-orange)

## What It Does

SentinelAI learns what "normal" looks like on your 
specific machine, then detects and explains behavioral 
anomalies in plain English using a local LLM.

- **Real-time health monitoring** — CPU, RAM, disk 
  streamed live via WebSocket
- **Personal baseline learning** — builds YOUR normal 
  from historical data (not a global average)
- **Behavioral anomaly detection** — flags unusual 
  processes, resource spikes, pattern deviations
- **LLM-powered explanations** — Qwen3:8b explains 
  what's happening in plain English
- **RAG chat interface** — ask questions about your 
  system in natural language, answered from real data
- **Weekly PDF reports** — automated health summaries 
  with anomaly logs and process analysis
- **Face detection module** — optional webcam-based 
  intruder detection (toggle on/off)
- **HCAI throughout** — every alert requires human 
  approval before being confirmed

## Architecture

React (Vite + Tailwind + Recharts)
↕ WebSocket + REST API
FastAPI (Python 3.11)
↕
SQLite (SQLAlchemy) ← psutil + pynput
↕
Ollama → Qwen3:8b (local, offline)

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React, Vite, Tailwind CSS, Recharts |
| Backend | FastAPI, Python 3.11, Uvicorn |
| Database | SQLite, SQLAlchemy |
| System | psutil, pynput |
| LLM | Ollama, Qwen3:8b |

## Setup

```bash
# Clone
git clone https://github.com/Prathik-c/SentinelAI.git
cd SentinelAI

# Backend
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt

# Create .env (copy from .env.example)
# Start Ollama: ollama run qwen3:8b

# Run backend
uvicorn main:app --reload

# Frontend (new terminal)
cd frontend
npm install
npm run dev
```

## Key Design Decisions

**Personal baseline, not global** — what's normal on a 
gaming laptop is different from a developer's machine. 
Every user's baseline is learned from their own data.

**Background logging independent of frontend** — 
monitoring runs continuously as an asyncio background 
task regardless of whether the dashboard is open.

**Face detection as optional module** — identified that 
webcam quality and CPU-only inference created 
inconsistent accuracy. Kept as a toggleable feature 
rather than a core dependency.

**RAG over pure LLM** — chat answers are grounded in 
real SQLite data to eliminate hallucination on 
system-specific questions.

**WAL mode SQLite** — Write-Ahead Logging prevents 
database corruption during frequent writes.

## Project Status

- ✅ Phases 0-5 complete and working
- 🔄 Phase 6: Fine-tuning pipeline (in progress)
- ⏳ Phase 7: Polish and deployment packaging