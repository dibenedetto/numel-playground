@echo off
setlocal EnableDelayedExpansion
:: =============================================================================
:: Numel Playground - Windows launcher
:: Installs uv (if missing), downloads Python 3.12, syncs dependencies from
:: uv.lock, then starts the application.
:: Usage:  run.bat [app arguments...]
:: =============================================================================

set UV_PYTHON=3.12
set SCRIPT_DIR=%~dp0
set "UV_CACHE_DIR=%SCRIPT_DIR%.uv-cache"
set "UV_PYTHON_INSTALL_DIR=%SCRIPT_DIR%.uv-python"
if not exist "%UV_CACHE_DIR%" mkdir "%UV_CACHE_DIR%" >nul 2>&1
if not exist "%UV_PYTHON_INSTALL_DIR%" mkdir "%UV_PYTHON_INSTALL_DIR%" >nul 2>&1

:: 1. Ensure uv is available
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo [numel] uv not found -- installing...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "irm https://astral.sh/uv/install.ps1 | iex"
    :: Refresh PATH from registry so we can find uv immediately
    for /f "tokens=*" %%i in ('powershell -NoProfile -Command ^
        "[System.Environment]::GetEnvironmentVariable(\"PATH\",\"User\")"') do (
        set "PATH=%%i;%PATH%"
    )
    where uv >nul 2>&1
    if !errorlevel! neq 0 (
        echo [numel] ERROR: uv installation failed. Please install manually:
        echo         https://docs.astral.sh/uv/getting-started/installation/
        exit /b 1
    )
    for /f "delims=" %%v in ('uv --version') do echo [numel] uv installed: %%v
) else (
    for /f "delims=" %%v in ('uv --version') do echo [numel] uv found: %%v
)

:: 2. Ensure Python 3.12 is available
cd /d "%SCRIPT_DIR%"
echo [numel] Checking Python %UV_PYTHON%...
uv python install %UV_PYTHON% --install-dir "%UV_PYTHON_INSTALL_DIR%" --quiet

:: 3. Sync dependencies (create / update .venv)
echo [numel] Syncing dependencies...
uv sync --frozen --quiet

:: 4. Run the application
echo [numel] Starting Numel Playground...
uv run --no-sync --frozen python app\app.py %*
