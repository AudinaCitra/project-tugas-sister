@echo off
cd /d "%~dp0"
echo FaktaLens - Tugas 2
python -m pip install -r requirements.txt
if not exist .env (
  copy .env.example .env >nul
  echo.
  echo File .env dibuat. Buka .env, isi API key Google, lalu jalankan bat ini lagi.
  pause
  exit /b
)
python app.py
pause
