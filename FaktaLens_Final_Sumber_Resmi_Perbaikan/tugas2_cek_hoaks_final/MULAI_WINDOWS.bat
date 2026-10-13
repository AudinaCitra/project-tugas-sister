@echo off
cd /d "%~dp0"
if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo File .env dibuat. Isi GOOGLE_FACTCHECK_API_KEY terlebih dahulu.
  notepad ".env"
)
echo Menyiapkan library Python...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo Gagal instal library. Cek koneksi internet dan Python.
  pause
  exit /b 1
)
echo.
echo Aplikasi berjalan di http://127.0.0.1:5001
echo Tekan CTRL+C untuk menghentikan server.
python app.py
pause
