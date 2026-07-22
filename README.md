# Arturo — Annunci Moda AI 👕✨

Trasforma le foto di un indumento in un annuncio professionale pronto per
Vinted e Catawiki: descrizioni, misure, prezzo consigliato e 4 foto
professionali fedeli all'originale. Poi precompila l'annuncio sul sito —
tu controlli e clicchi Pubblica.

## Installazione (5 minuti, solo la prima volta)

1. **Installa Python** (se non ce l'hai): scaricalo da
   [python.org/downloads](https://www.python.org/downloads/) e durante
   l'installazione **spunta la casella "Add Python to PATH"**.

2. **Scarica questa cartella** sul tuo PC (o clonala con git).

3. **Fai doppio click su `run.bat`** — la prima volta scarica tutto da solo
   (qualche minuto), poi apre l'app nel browser.

## Chiave API (necessaria)

L'app usa l'intelligenza artificiale di **Google Gemini** (consigliata,
~0,16 € per annuncio). Serve una chiave personale:

1. Vai su [aistudio.google.com](https://aistudio.google.com) → **Get API key**
   e crea la chiave col tuo account Google
2. Su [ai.studio/projects](https://ai.studio/projects) carica qualche euro di
   credito prepagato (senza credito la chiave non genera immagini)
3. Inserisci la chiave nella pagina dell'app, sezione
   **"🔑 Imposta la tua API Key"** (viene salvata solo nel tuo browser)

In alternativa crea un file `.env` nella cartella con dentro:
`GEMINI_API_KEY=...` (vedi `.env.example`).

**Costo indicativo**: ~0,16 € di API per annuncio completo (analisi + 4 foto).

<details>
<summary>Preferisci OpenAI? (alternativa, più costosa)</summary>

Funziona anche con una chiave OpenAI di
[platform.openai.com](https://platform.openai.com) → API Keys: mettila
nella stessa sezione dell'app, oppure nel `.env` come
`OPENAI_API_KEY=sk-...` insieme a `AI_PROVIDER=openai`.
Costo: ~0,80 € per annuncio in qualità massima
(~0,30 € con `IMAGE_QUALITY=medium`).
</details>

## Come si usa

1. Doppio click su `run.bat` → si apre http://localhost:8000
2. Trascina 2–4 foto del capo (fronte, retro, dettaglio stampa, etichetta:
   più foto = immagini generate più fedeli)
3. Clicca **Genera descrizione e immagini** e aspetta 1–2 minuti
4. Copia i testi, scarica le foto, oppure clicca **Pubblica su Vinted/Catawiki**:
   si apre una finestra Chrome, la prima volta fai il login tu (resta
   memorizzato), l'app compila l'annuncio e **tu controlli e pubblichi**

## Metti Arturo online (per condividerlo con un link)

Il progetto è già pronto per [Railway](https://railway.app) (c'è `railway.toml`)
o qualsiasi host che legga il `Procfile` (Render, Heroku...):

1. Carica il repository su GitHub e collegalo a Railway (New Project → Deploy from GitHub)
2. Nelle **Variables** del servizio imposta:
   - `GEMINI_API_KEY` = la tua chiave (sarà usata da chi apre il link)
   - `APP_PASSWORD` = una password a tua scelta — **importante**: senza,
     chiunque trovi il link genera annunci a tue spese
   - (opzionale) `RATE_LIMIT_PER_HOUR` = max annunci per persona/ora (default 12)
3. Manda al tuo amico il link **e la password**: alla prima analisi
   gliela chiede e poi la ricorda nel suo browser

Online funzionano analisi, testi, misure e le 4 immagini (copia/scarica).
I bottoni "Pubblica su Vinted/Catawiki" compaiono solo quando l'app gira
sul PC (devono aprire una finestra del browser).

## Note

- La pubblicazione automatica funziona solo con l'app installata sul PC
  (deve aprire una finestra del browser sul tuo schermo).
- Su Catawiki i lotti passano sempre dall'approvazione dei loro esperti.
- L'ultimo annuncio generato resta salvato: bottone "↩ Riapri ultimo annuncio".
