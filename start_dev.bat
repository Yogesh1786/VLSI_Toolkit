@echo off
REM Developer mode: API server with auto-reload + React dev server with instant updates.
REM Edit Python or React code and the running app picks up the change by itself.
cd /d "%~dp0"
if not exist "web\node_modules" (
  echo Installing frontend packages...
  pushd web & call npm install & popd
)
echo Starting API server (auto-reload) on http://localhost:8000 ...
start "VLSI Toolkit API (close to stop)" cmd /k python -m uvicorn api.main:app --port 8000 --reload
echo Starting React dev server on http://localhost:5173 ...
start "VLSI Toolkit web (close to stop)" cmd /k npm --prefix web run dev
timeout /t 4 >nul
start "" http://localhost:5173
