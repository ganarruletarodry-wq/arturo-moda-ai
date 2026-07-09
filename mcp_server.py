"""
Arturo MCP Server — espone le funzionalità OpenAI come strumenti per Claude.

Strumenti disponibili:
  • analizza_indumento      — GPT-4o Vision: analizza foto di un indumento
  • genera_immagini_moda    — DALL-E 3: genera immagini prodotto (modella + sfondo bianco)
  • crea_annuncio_completo  — pipeline completa: analisi + 4 immagini
  • chat                    — chat generica con GPT-4o
  • genera_immagine         — genera una singola immagine con DALL-E 3
  • lista_modelli           — elenca i modelli OpenAI disponibili
"""

import os
import base64
import json
import uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import openai
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from services.image_service import generate_clothing_images

load_dotenv()

mcp = FastMCP("arturo-openai")
GENERATED_DIR = Path("generated")
GENERATED_DIR.mkdir(exist_ok=True)


def _client() -> openai.OpenAI:
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise ValueError("OPENAI_API_KEY non impostata nel file .env")
    return openai.OpenAI(api_key=key)


def _encode_image(path: str) -> tuple[str, str]:
    p = Path(path)
    media_types = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".webp": "image/webp",
    }
    mt = media_types.get(p.suffix.lower(), "image/jpeg")
    data = base64.standard_b64encode(p.read_bytes()).decode()
    return data, mt


# ---------------------------------------------------------------------------
# TOOL 1 — Analisi indumento con GPT-4o Vision
# ---------------------------------------------------------------------------
@mcp.tool()
def analizza_indumento(percorsi_immagini: list[str]) -> str:
    """
    Analizza le foto di un indumento e restituisce un JSON con titolo, categoria,
    genere, colori, materiale, taglia, brand, condizione, descrizioni per Vinted
    e Catawiki, hashtag, prezzo suggerito e prompt per DALL-E.

    Args:
        percorsi_immagini: Lista di percorsi file immagine (max 4).
                           Formati: JPG, PNG, WEBP.

    Returns:
        JSON string con tutti i campi dell'annuncio.
    """
    client = _client()
    content: list[dict] = []

    for path in percorsi_immagini[:4]:
        data, mt = _encode_image(path)
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mt};base64,{data}", "detail": "high"},
        })

    content.append({"type": "text", "text": """Analizza questo indumento e rispondi con JSON:
{
  "titolo": "Titolo max 60 caratteri",
  "categoria": "es. Maglione, Jeans, Vestito...",
  "genere": "Uomo / Donna / Unisex / Bambino",
  "colori": ["colore1"],
  "materiale": "materiale o ''",
  "taglia": "taglia o ''",
  "brand": "brand o ''",
  "condizione": "Nuovo con etichetta / Ottimo / Buono / Discreto",
  "descrizione_vinted": "max 300 parole, tono giovane, con emoji",
  "descrizione_catawiki": "max 400 parole, formale e dettagliata",
  "hashtag": ["#tag1","#tag2","#tag3","#tag4","#tag5"],
  "prezzo_suggerito_min": 0,
  "prezzo_suggerito_max": 0,
  "prompt_immagine_modella": "English prompt for gpt-image-1 showing model wearing item",
  "prompt_sfondo_bianco": "English prompt for gpt-image-1 product shot on white background"
}
Rispondi SOLO con il JSON, niente altro."""})

    resp = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=2048,
        messages=[
            {"role": "system", "content": "Sei un esperto di moda e vendita online. Rispondi solo con JSON valido."},
            {"role": "user", "content": content},
        ],
    )
    raw = resp.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


# ---------------------------------------------------------------------------
# TOOL 2 — Genera immagini moda con DALL-E 3
# ---------------------------------------------------------------------------
@mcp.tool()
def genera_immagini_moda(
    prompt_modella: str,
    prompt_sfondo_bianco: str,
    percorsi_riferimento: list[str] | None = None,
) -> str:
    """
    Genera 4 immagini professionali per un annuncio di moda con gpt-image-1:
    - 2 immagini con modella che indossa l'indumento (fronte + lifestyle)
    - 2 immagini prodotto su sfondo bianco (flat lay + appendiabiti)

    IMPORTANTE: passa sempre percorsi_riferimento (le foto reali del capo) quando
    disponibili — con le foto di riferimento l'indumento generato resta identico
    all'originale (images.edit + input_fidelity=high). Senza, viene inventato dal testo.

    Args:
        prompt_modella: Descrizione in inglese dell'indumento per le foto con modella.
        prompt_sfondo_bianco: Descrizione in inglese per le foto prodotto su sfondo bianco.
        percorsi_riferimento: Percorsi delle foto originali del capo (max 4, consigliato).

    Returns:
        JSON string con i percorsi dei file generati nella cartella 'generated/'.
    """
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise ValueError("OPENAI_API_KEY non impostata nel file .env")

    if percorsi_riferimento:
        # Massima fedeltà: foto reali come riferimento
        filenames = generate_clothing_images(
            reference_image_paths=percorsi_riferimento,
            model_prompt=prompt_modella,
            product_prompt=prompt_sfondo_bianco,
            api_key=key,
        )
        result = {k: str(GENERATED_DIR / f) for k, f in filenames.items()}
        return json.dumps(result, ensure_ascii=False)

    # Fallback solo-testo (l'indumento è ricostruito dalla descrizione)
    client = _client()
    prompts = {
        "model_front": (
            f"Professional fashion photography. A stylish model wearing {prompt_modella}. "
            f"Front view, standing straight, full body shot. Studio lighting, clean neutral "
            f"background, high-end fashion magazine style, sharp focus."
        ),
        "model_lifestyle": (
            f"Professional fashion photography. A stylish model wearing {prompt_modella}. "
            f"Three-quarter view, natural casual pose, lifestyle fashion photo. Natural lighting, "
            f"urban background, editorial fashion style, sharp focus."
        ),
        "product_flat": (
            f"Professional product photography. {prompt_sfondo_bianco}. "
            f"Flat lay on pure white background, perfectly arranged, e-commerce style, "
            f"bright even lighting, no shadows, shot from directly above."
        ),
        "product_hanger": (
            f"Professional product photography. {prompt_sfondo_bianco}. "
            f"Displayed on wooden hanger on pure white background, e-commerce style, "
            f"bright even lighting, slight soft shadow, front view."
        ),
    }

    def _one(item: tuple[str, str]) -> tuple[str, str]:
        k, prompt = item
        resp = client.images.generate(
            model="gpt-image-1", prompt=prompt,
            size="1024x1024", quality="high", n=1,
        )
        filename = f"{uuid.uuid4().hex}_{k}.png"
        (GENERATED_DIR / filename).write_bytes(base64.b64decode(resp.data[0].b64_json))
        return k, str(GENERATED_DIR / filename)

    with ThreadPoolExecutor(max_workers=4) as ex:
        result = dict(ex.map(_one, prompts.items()))

    return json.dumps(result, ensure_ascii=False)


# ---------------------------------------------------------------------------
# TOOL 3 — Pipeline completa: analisi + generazione immagini
# ---------------------------------------------------------------------------
@mcp.tool()
def crea_annuncio_completo(percorsi_immagini: list[str]) -> str:
    """
    Pipeline completa: analizza le foto dell'indumento con GPT-4o e genera
    automaticamente le 4 immagini professionali con DALL-E 3.

    Args:
        percorsi_immagini: Lista di percorsi file immagine dell'indumento (max 4).

    Returns:
        JSON string con 'analisi' (tutti i dati dell'annuncio) e 'immagini' (percorsi file).
    """
    analisi_raw = analizza_indumento(percorsi_immagini)
    analisi = json.loads(analisi_raw)

    immagini_raw = genera_immagini_moda(
        prompt_modella=analisi.get("prompt_immagine_modella", ""),
        prompt_sfondo_bianco=analisi.get("prompt_sfondo_bianco", ""),
        percorsi_riferimento=percorsi_immagini,
    )

    return json.dumps({
        "analisi": analisi,
        "immagini": json.loads(immagini_raw),
    }, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# TOOL 4 — Chat generica con GPT-4o
# ---------------------------------------------------------------------------
@mcp.tool()
def chat(
    messaggio: str,
    modello: str = "gpt-4o",
    temperatura: float = 0.7,
) -> str:
    """
    Invia un messaggio a GPT-4o (o altro modello OpenAI) e restituisce la risposta.

    Args:
        messaggio: Il testo del messaggio da inviare.
        modello: Modello da usare (default: gpt-4o). Es: gpt-4o-mini, gpt-4o.
        temperatura: Creatività 0.0–2.0 (default: 0.7).

    Returns:
        Risposta testuale del modello.
    """
    client = _client()
    resp = client.chat.completions.create(
        model=modello,
        temperature=temperatura,
        messages=[{"role": "user", "content": messaggio}],
    )
    return resp.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# TOOL 5 — Genera una singola immagine con gpt-image-1
# ---------------------------------------------------------------------------
@mcp.tool()
def genera_immagine(
    prompt: str,
    dimensioni: str = "1024x1024",
    qualita: str = "high",
) -> str:
    """
    Genera una singola immagine con gpt-image-1 e la salva nella cartella 'generated/'.

    Args:
        prompt: Descrizione in inglese dell'immagine da generare.
        dimensioni: '1024x1024', '1536x1024' o '1024x1536' (default: 1024x1024).
        qualita: 'low', 'medium' o 'high' (default: high).

    Returns:
        Percorso del file immagine generato.
    """
    client = _client()
    resp = client.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        size=dimensioni,
        quality=qualita,
        n=1,
    )
    filename = f"{uuid.uuid4().hex}_custom.png"
    filepath = GENERATED_DIR / filename
    filepath.write_bytes(base64.b64decode(resp.data[0].b64_json))
    return str(filepath)


# ---------------------------------------------------------------------------
# TOOL 6 — Lista modelli disponibili
# ---------------------------------------------------------------------------
@mcp.tool()
def lista_modelli() -> str:
    """
    Elenca tutti i modelli OpenAI disponibili per il tuo account API.

    Returns:
        JSON string con lista di ID modelli ordinata alfabeticamente.
    """
    client = _client()
    models = client.models.list()
    ids = sorted(m.id for m in models.data)
    return json.dumps(ids, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Avvio server
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    mcp.run()
