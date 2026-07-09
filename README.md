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

## Chiave OpenAI (necessaria)

L'app usa l'intelligenza artificiale di OpenAI, serve una chiave personale:

1. Vai su [platform.openai.com](https://platform.openai.com) → API Keys → Create new key
2. Inseriscila nella pagina dell'app, sezione **"🔑 Imposta la tua API Key"**
   (viene salvata solo nel tuo browser)

In alternativa crea un file `.env` nella cartella con dentro:
`OPENAI_API_KEY=sk-...` (vedi `.env.example`).

**Costo indicativo**: ~0,80 € di API per annuncio completo in qualità massima
(~0,30 € impostando `IMAGE_QUALITY=medium` nel `.env`).

## Come si usa

1. Doppio click su `run.bat` → si apre http://localhost:8000
2. Trascina 2–4 foto del capo (fronte, retro, dettaglio stampa, etichetta:
   più foto = immagini generate più fedeli)
3. Clicca **Genera descrizione e immagini** e aspetta 1–2 minuti
4. Copia i testi, scarica le foto, oppure clicca **Pubblica su Vinted/Catawiki**:
   si apre una finestra Chrome, la prima volta fai il login tu (resta
   memorizzato), l'app compila l'annuncio e **tu controlli e pubblichi**

## Note

- La pubblicazione automatica funziona solo con l'app installata sul PC
  (deve aprire una finestra del browser sul tuo schermo).
- Su Catawiki i lotti passano sempre dall'approvazione dei loro esperti.
- L'ultimo annuncio generato resta salvato: bottone "↩ Riapri ultimo annuncio".
