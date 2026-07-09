# Arturo — Annunci Moda AI

App web che trasforma foto di indumenti in annunci professionali per Vinted, Catawiki, Subito e simili.
Usa **GPT-4o Vision** per l'analisi e **gpt-image-1** (`images.edit` con `input_fidelity=high`) per
generare immagini professionali mantenendo l'indumento identico alle foto originali.

## Stack

| Layer | Tecnologia |
|-------|-----------|
| Backend | Python 3.14, FastAPI, uvicorn |
| AI Vision | OpenAI GPT-4o (analisi foto) |
| AI Immagini | OpenAI gpt-image-1 via `images.edit` + `input_fidelity=high` (4 foto fedeli all'originale) |
| Pubblicazione | Playwright (automazione Vinted/Catawiki, sperimentale) |
| Frontend | HTML + CSS + JavaScript puro |
| MCP Server | `mcp` SDK Python 1.27+ |

## Struttura progetto

```
ARTURO/
├── main.py                          # FastAPI app — entry point web
├── mcp_server.py                    # MCP server — strumenti per Claude
├── services/
│   ├── openai_describe_service.py   # GPT-4o Vision: analisi indumento
│   ├── image_service.py             # gpt-image-1: 4 immagini fedeli (images.edit + input_fidelity)
│   ├── vinted_service.py            # Playwright: pubblicazione automatica su Vinted
│   └── catawiki_service.py          # Playwright: pubblicazione automatica su Catawiki
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
OPENAI_API_KEY=sk-...          # obbligatoria — platform.openai.com → API Keys
IMAGE_QUALITY=high             # opzionale: high (default, max fedeltà) | medium (più economico)
REQUIRE_CLIENT_KEY=true        # opzionale: su server pubblico, ogni utente usa la propria chiave
APP_PASSWORD=...               # opzionale: protegge analisi/pubblicazione (consigliata online)
PLAYWRIGHT_HEADLESS=true       # opzionale: obbligatorio su server senza display
GENERATED_MAX_AGE_DAYS=14      # opzionale: pulizia automatica immagini generate
```

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
Genera 4 immagini professionali con gpt-image-1. Passare sempre le foto originali
in `percorsi_riferimento` per mantenere l'indumento identico (images.edit + input_fidelity=high).
```
Input:  prompt_modella: str, prompt_sfondo_bianco: str  (in inglese)
        percorsi_riferimento: list[str] | None  — foto reali del capo (max 4, consigliato)
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
| POST | `/api/publish/vinted` | Precompila l'annuncio su Vinted in un browser visibile; l'utente controlla e pubblica (solo locale) |
| POST | `/api/publish/catawiki` | Precompila il lotto su Catawiki in un browser visibile; l'utente controlla e invia (solo locale) |
| GET | `/api/config` | Indica se il server ha già la chiave OpenAI |
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
| gpt-image-1 high + input_fidelity 1024×1024 × 4 | ~€0.70–0.80 |
| gpt-image-1 medium (`IMAGE_QUALITY=medium`) × 4 | ~€0.25–0.30 |
| **Totale per annuncio (high)** | **~€0.75–0.85** |
| **Totale per annuncio (medium)** | **~€0.30** |

## Roadmap

- [x] Analisi indumento con GPT-4o Vision
- [x] Generazione 4 immagini fedeli all'originale (gpt-image-1 + input_fidelity=high)
- [x] Descrizioni ottimizzate per Vinted e Catawiki
- [x] Misure stimate (petto, spalle, vita, fianchi, ecc.)
- [x] MCP server con 6 strumenti
- [x] Auto-upload annunci su Vinted/Catawiki (Playwright, sperimentale — captcha possibili)
- [ ] Storico annunci creati
- [ ] Supporto video/reels del prodotto
