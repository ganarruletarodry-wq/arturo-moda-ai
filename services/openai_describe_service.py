import openai
import base64
import json
import io
from pathlib import Path
from PIL import Image


SYSTEM_PROMPT = """Sei un esperto di moda e vendita online su piattaforme come Vinted, Catawiki, Subito e eBay.
Sei anche esperto di taglie e misure di abbigliamento di tutte le marche.
Quando ti mostro foto di un indumento, devi analizzarlo nel dettaglio e rispondere SOLO con un JSON valido, senza testo aggiuntivo prima o dopo."""

ANALYSIS_PROMPT = """Analizza attentamente queste foto dell'indumento e rispondi con un JSON nel seguente formato ESATTO:

{
  "titolo": "Titolo breve e accattivante per l'annuncio (max 60 caratteri)",
  "categoria": "Categoria dell'indumento (es: Maglione, Jeans, Vestito, Giacca, ecc.)",
  "genere": "Uomo / Donna / Unisex / Bambino",
  "colori": ["colore1", "colore2"],
  "materiale": "Materiale se visibile, altrimenti ''",
  "taglia": "Taglia se visibile sull'etichetta, altrimenti ''",
  "brand": "Brand/Marca se visibile, altrimenti ''",
  "condizione": "Nuovo con etichetta / Nuovo senza etichetta / Ottimo / Buono / Discreto",
  "misure": {
    "petto_busto": "es. 92-96 cm oppure null se non applicabile",
    "spalle": "es. 44-46 cm oppure null se non applicabile",
    "vita": "es. 76-80 cm oppure null se non applicabile",
    "fianchi": "es. 96-100 cm oppure null se non applicabile",
    "lunghezza_totale": "es. 70-74 cm oppure null se non applicabile",
    "lunghezza_gamba": "es. 78-82 cm oppure null se non applicabile",
    "maniche": "es. 60-64 cm oppure null se non applicabile",
    "note_misure": "Spiega come hai stimato le misure: es. 'Stimate dalla taglia M visibile in etichetta e dalle proporzioni visive'"
  },
  "descrizione_vinted": "Descrizione ottimizzata per Vinted, tono giovane e diretto, max 300 parole. Includi: cosa è, colore, materiale, condizione, abbinamenti consigliati. NON includere le misure nel testo (le mostriamo separatamente). Usa emoji appropriati.",
  "descrizione_catawiki": "Descrizione formale e dettagliata per Catawiki, max 400 parole. Descrivi ogni dettaglio: tessuto, cuciture, chiusure, tasche, particolarità. NON includere le misure nel testo (le mostriamo separatamente).",
  "hashtag": ["#hashtag1", "#hashtag2", "#hashtag3", "#hashtag4", "#hashtag5"],
  "prezzo_suggerito_min": 5,
  "prezzo_suggerito_max": 30,
  "prompt_immagine_modella": "Prompt in inglese per gpt-image-1: descrivi l'indumento in dettaglio per generare una foto di una modella che lo indossa. Sii molto specifico su colori, stile, forma.",
  "prompt_sfondo_bianco": "Prompt in inglese per gpt-image-1: descrivi l'indumento in dettaglio per generare una foto prodotto su sfondo bianco. Stile e-commerce professionale."
}

ISTRUZIONI PER LE MISURE:
- Stima le misure basandoti su: taglia sull'etichetta (se visibile), brand noto (usa le tabelle taglie ufficiali), proporzioni visive dell'indumento
- Usa range di 4 cm (es. 92-96) per dare margine di errore onesto
- Metti null per misure non applicabili alla categoria (es. lunghezza_gamba per una giacca)
- Sii preciso: una taglia M da Zara è diversa da una M da H&M

Tutti i valori devono essere in italiano tranne i due prompt per gpt-image-1 che devono essere in inglese.
Rispondi SOLO con il JSON, niente altro."""

MAX_IMAGE_PX = 1024


def _encode_image(image_path: str) -> tuple[str, str]:
    img = Image.open(image_path).convert("RGB")
    if max(img.size) > MAX_IMAGE_PX:
        img.thumbnail((MAX_IMAGE_PX, MAX_IMAGE_PX), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    data = base64.standard_b64encode(buf.getvalue()).decode("utf-8")
    return data, "image/jpeg"


def analyze_clothing(image_paths: list[str], api_key: str) -> dict:
    client = openai.OpenAI(api_key=api_key)

    content: list[dict] = []
    for path in image_paths[:4]:
        data, media_type = _encode_image(path)
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{media_type};base64,{data}", "detail": "high"},
        })
    content.append({"type": "text", "text": ANALYSIS_PROMPT})

    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=3000,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
    )

    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())
