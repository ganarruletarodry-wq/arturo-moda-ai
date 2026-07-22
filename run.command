#!/bin/bash
# Avvio rapido per macOS — doppio click (la prima volta: tasto destro → Apri)
cd "$(dirname "$0")"

echo "============================================"
echo "  Arturo - Annunci Moda AI"
echo "============================================"
echo

# --- Controlla Python ---
if ! command -v python3 >/dev/null 2>&1; then
    echo "ERRORE: Python non trovato!"
    echo "Scaricalo da https://www.python.org/downloads/ e installalo."
    echo
    read -r -p "Premi Invio per chiudere"
    exit 1
fi

# --- Prima installazione: dipendenze + browser Playwright ---
if [ ! -f ".installed" ]; then
    echo "Prima installazione: scarico le dipendenze..."
    if ! python3 -m pip install -r requirements.txt -q; then
        echo "ERRORE durante l'installazione delle dipendenze."
        read -r -p "Premi Invio per chiudere"
        exit 1
    fi
    echo "Scarico il browser per la pubblicazione automatica..."
    python3 -m playwright install chromium
    echo ok > .installed
    echo "Installazione completata!"
    echo
fi

# --- File .env ---
if [ ! -f ".env" ]; then
    echo "NOTA: file .env non trovato."
    echo "Puoi comunque usare l'app inserendo la tua chiave API"
    echo "direttamente nella pagina web (sezione \"Imposta la tua API Key\")."
    echo
fi

echo "App disponibile su: http://localhost:8000"
echo "Premi Ctrl+C in questa finestra per fermarla."
echo

(sleep 2 && open http://localhost:8000) &
python3 -m uvicorn main:app --port 8000
