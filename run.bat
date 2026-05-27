@echo off
echo Avvio Arturo - Annunci Moda AI...
echo.

cd /d "%~dp0"

if not exist ".env" (
    echo ATTENZIONE: file .env non trovato!
    echo Copia .env.example in .env e inserisci le tue API key.
    echo.
)

pip install -r requirements.txt -q

echo.
echo App disponibile su: http://localhost:8000
echo Premi Ctrl+C per fermare.
echo.

python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
pause
