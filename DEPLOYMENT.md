# SentinelAI Deployment & Executable Compilation Guide

This document describes installation prerequisites, local deployment, and instructions for compiling SentinelAI into a standalone Windows executable.

---

## 1. Local Development Installation

### Prerequisites
1. **Python**: Version `3.10` or higher.
2. **Node.js & npm**: Installed for the React dashboard.
3. **Ollama**: Installed from [Ollama.com](https://ollama.com).

### Installation Steps
1. Open Windows Command Prompt/PowerShell in the project root.
2. Install Python package in editable developer mode:
   ```bash
   pip install -e .
   ```
3. Initialize the frontend packages:
   ```bash
   cd frontend
   npm install
   cd ..
   ```
4. Start SentinelAI:
   ```bash
   sentinelai start
   ```

---

## 2. Production Executable Compilation

To distribute SentinelAI as a standalone Windows application without requiring users to install Python or Node manually, you can compile the package using **PyInstaller** or **Nuitka**.

### Option A: PyInstaller

1. **Install PyInstaller**:
   ```bash
   pip install pyinstaller
   ```
2. **Compile the App**:
   Create a single folder bundle containing the FastAPI backend, CLI, and necessary assets. Run PyInstaller pointing to the entry point wrapper:
   ```bash
   pyinstaller --onedir --name sentinelai --add-data "backend;backend" --add-data "sentinelai.yaml;." sentinelai_cli/main.py
   ```
   - `--onedir`: Generates a folder structure containing all executable DLLs and binaries (better startup speed than single-file for complex apps).
   - `--add-data`: Bundle the backend modules inside the executable structure.

### Option B: Nuitka

Nuitka compiles Python code directly into C-level binaries for extreme performance and obfuscation.

1. **Install Nuitka**:
   ```bash
   pip install nuitka
   ```
2. **Compile**:
   ```bash
   python -m nuitka --standalone --show-progress --plugin-enable=pydanticv2 --include-data-dir=backend=backend sentinelai_cli/main.py
   ```

### Bundling React Frontend Assets
For a production build, compile the Vite UI assets and host them statically via FastAPI:
1. Run `npm run build` inside `frontend/`.
2. Move the generated `dist/` index files into static mounts inside `backend/main.py` using `fastapi.staticfiles.StaticFiles`.
3. Re-run PyInstaller/Nuitka ensuring the `dist` static folder is bundled inside `--add-data`.
