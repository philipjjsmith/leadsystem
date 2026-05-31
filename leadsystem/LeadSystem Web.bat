@echo off
cd /d "C:\Users\phili\leadsystem\leadsystem"
set PYTHONUTF8=1
echo Starting LeadSystem Web Dashboard...
echo Open http://localhost:8000 in your browser (opens automatically)
echo Press Ctrl+C to stop.
echo.
python main.py serve
pause
