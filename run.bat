@echo off
title Arturo - Annunci Moda AI
cd /d "%~dp0"

echo ============================================
echo   Arturo - Annunci Moda AI
echo ============================================
echo.

REM --- Controlla Python ---
python --version >nul 2>&1
if errorlevel 1 (
    echo ERRORE: Python non trovato!
    echo Scaricalo da https://www.python.org/downloads/
    echo Durante l'installazione spunta "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

REM --- Prima installazione: dipendenze + browser Playwright ---
if not exist ".installed" (
    echo Prima installazione: scarico le dipendenze...
    pip install -r requirements.txt -q
    if errorlevel 1 (
        echo ERRORE durante l'installazione delle dipendenze.
        pause
        exit /b 1
    )
    echo Scarico il browser per la pubblicazione automatica...
    python -m playwright install chromium
    echo ok > .installed
    echo Installazione completata!
    echo.
)

REM --- File .env ---
if not exist ".env" (
    echo NOTA: file .env non trovato.
    echo Puoi comunque usare l'app inserendo la tua chiave OpenAI
    echo direttamente nella pagina web ^(sezione "Imposta la tua API Key"^).
    echo.
)

echo App disponibile su: http://localhost:8000
echo Premi Ctrl+C in questa finestra per fermarla.
echo.

start "" http://localhost:8000
python -m uvicorn main:app --port 8000
pause
