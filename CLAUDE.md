# Arturo — Annunci Moda AI

App web che trasforma foto di indumenti in annunci professionali per Vinted, Catawiki, Subito e simili.
Usa **GPT-4o Vision** per l'analisi e **DALL-E 3** per generare immagini professionali.

## Stack

| Layer | Tecnologia |
|-------|-----------|
| Backend | Python 3.14, FastAPI, uvicorn |
| AI Vision | OpenAI GPT-4o (analisi foto) |
| AI Immagini | OpenAI DALL-E 3 (generazione 4 foto) |
| Frontend | HTML + CSS + JavaScript puro |
| MCP Server | `mcp` SDK Python 1.27+ |

## Struttura progetto

```
ARTURO/
├── main.py                          # FastAPI app — entry point web
├── mcp_server.py                    # MCP server — strumenti per Claude
├── services/
│   ├── openai_describe_service.py   # GPT-4o Vision: analisi indumento
│   └── image_service.py             # DALL-E 3: generazione 4 immagini
├── frontend/
│   ├── index.html                   # UI principale
│   ├── style.css                    # Design
│   └── app.js                       # Logica frontend
├── uploads/                         # Foto caricate (temporanee, auto-cancellate)
├── generated/                       # Immagini generate da DALL-E 3
├── .env                             # API key reale (NON committare)
├── .env.example                     # Template variabili ambiente
├── requirements.txt
└── run.bat                          # Avvio rapido Windows
```

## Variabili ambiente

File `.env` nella root del progetto:

```
OPENAI_API_KEY=sk-...
```

Una sola chiave necessaria (OpenAI). Ottienila su platform.openai.com → API Keys.

## Avvio app web

```bash
# Installa dipendenze (prima volta)
pip install -r requirements.txt

# Avvia il server
python -m uvicorn main:app --reload --port 8000
```

Oppure doppio click su `run.bat`.
App disponibile su: **http://localhost:8000**

## Avvio MCP server

Per usare gli strumenti OpenAI direttamente da Claude Code:

```bash
python mcp_server.py
```

Oppure configuralo in Claude Desktop / Claude Code settings come descritto sotto.

## Configurazione MCP in Claude Code

Aggiungi al file `.claude/settings.json` del progetto:

```json
{
  "mcpServers": {
    "arturo-openai": {
      "command": "python",
      "args": ["mcp_server.py"],
      "cwd": "C:/Users/Usuario/Desktop/PROGETTI/ARTURO"
    }
  }
}
```

Oppure per Claude Desktop, in `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "arturo-openai": {
      "command": "python",
      "args": ["C:/Users/Usuario/Desktop/PROGETTI/ARTURO/mcp_server.py"]
    }
  }
}
```

## Strumenti MCP disponibili

### `analizza_indumento`
Analizza foto di un indumento con GPT-4o Vision.
```
Input:  percorsi_immagini: list[str]  — percorsi file locali (max 4)
Output: JSON con titolo, categoria, genere, colori, materiale, taglia, brand,
        condizione, descrizione_vinted, descrizione_catawiki, hashtag,
        prezzo_suggerito_min/max, prompt_immagine_modella, prompt_sfondo_bianco
```

### `genera_immagini_moda`
Genera 4 immagini professionali con DALL-E 3.
```
Input:  prompt_modella: str, prompt_sfondo_bianco: str  (in inglese)
Output: JSON con percorsi dei 4 file PNG generati in generated/
        Chiavi: model_front, model_lifestyle, product_flat, product_hanger
```

### `crea_annuncio_completo`
Pipeline completa in un solo strumento: analisi + 4 immagini.
```
Input:  percorsi_immagini: list[str]
Output: JSON { "analisi": {...}, "immagini": {"model_front": "...", ...} }
```

### `chat`
Chat generica con GPT-4o o qualsiasi modello OpenAI.
```
Input:  messaggio: str, modello: str = "gpt-4o", temperatura: float = 0.7
Output: str — risposta del modello
```

### `genera_immagine`
Genera una singola immagine con DALL-E 3.
```
Input:  prompt: str, dimensioni: str = "1024x1024", qualita: str = "standard"
Output: str — percorso del file PNG generato
```

### `lista_modelli`
Elenca tutti i modelli OpenAI disponibili sull'account.
```
Output: JSON array di ID modelli
```

## API web endpoints

| Metodo | Path | Descrizione |
|--------|------|-------------|
| POST | `/api/analyze` | Analisi + generazione immagini |
| GET | `/api/image/{filename}` | Visualizza immagine generata |
| GET | `/api/download/{filename}` | Scarica immagine generata |
| GET | `/health` | Health check |
| GET | `/docs` | Swagger UI (FastAPI auto-generato) |

### Esempio chiamata `/api/analyze`

```bash
curl -X POST http://localhost:8000/api/analyze \
  -F "files=@foto_vestito.jpg" \
  -F "openai_key=sk-..."
```

## Flusso dati

```
Foto utente → uploads/ (temporaneo)
     ↓
GPT-4o Vision → JSON analisi indumento
     ↓
DALL-E 3 × 4 → generated/*.png
     ↓
Frontend mostra risultati (copia/scarica)
     ↓
uploads/ pulito automaticamente dopo elaborazione
```

## Costi indicativi OpenAI

| Operazione | Costo stimato |
|-----------|--------------|
| GPT-4o Vision (analisi 1-4 foto) | ~€0.01–0.03 |
| DALL-E 3 standard 1024×1024 × 4 | ~€0.16 |
| **Totale per annuncio** | **~€0.17–0.20** |

## Roadmap

- [x] Analisi indumento con GPT-4o Vision
- [x] Generazione 4 immagini con DALL-E 3
- [x] Descrizioni ottimizzate per Vinted e Catawiki
- [x] MCP server con 6 strumenti
- [ ] Auto-upload annunci su Vinted (automazione browser)
- [ ] Auto-upload annunci su Catawiki
- [ ] Storico annunci creati
- [ ] Supporto video/reels del prodotto
