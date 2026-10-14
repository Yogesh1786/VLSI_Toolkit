@echo off
REM Double-click to start the VLSI Toolkit (React frontend + Python API) at http://localhost:8000
cd /d "%~dp0"
if not exist "web\dist\index.html" (
  echo First run: building the React frontend...
  pushd web
  if not exist node_modules call npm install
  call npm run build
  popd
)
echo Starting VLSI Toolkit at http://localhost:8000  (close this window to stop)
start "" http://localhost:8000
python -m uvicorn api.main:app --port 8000
