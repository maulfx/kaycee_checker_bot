@echo off
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo   🎬 TikTok Video Analyzer Bot - Setup
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

:: Check Python
echo.
echo [1/4] Mengecek Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python tidak ditemukan!
    echo    Download dari: https://www.python.org/downloads/
    echo    Pastikan centang "Add Python to PATH" saat install!
    pause
    exit /b 1
)
python --version

:: Create venv
echo.
echo [2/4] Membuat virtual environment...
if not exist "venv" (
    python -m venv venv
    echo ✅ Virtual environment dibuat
) else (
    echo ✅ Virtual environment sudah ada
)

:: Activate venv and install deps
echo.
echo [3/4] Menginstall dependencies...
call venv\Scripts\activate.bat
pip install -r requirements.txt

:: Check .env
echo.
echo [4/4] Mengecek konfigurasi...
if not exist ".env" (
    copy .env.example .env
    echo.
    echo ⚠️  File .env telah dibuat dari template!
    echo    Buka file .env dan masukkan token bot dari @BotFather
    echo    Kemudian jalankan: python bot.py
) else (
    echo ✅ File .env ditemukan
    echo.
    echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    echo   Setup selesai! Jalankan bot dengan:
    echo     venv\Scripts\activate.bat
    echo     python bot.py
    echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
)

echo.
pause
