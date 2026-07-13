"""
Arturo MCP Server — espone le funzionalità OpenAI come strumenti per Claude.

Strumenti disponibili:
  • analizza_indumento      — GPT-4o Vision: analizza foto di un indumento
  • genera_immagini_moda    — gpt-image-1: genera immagini prodotto (modella + sfondo bianco)
  • crea_annuncio_completo  — pipeline completa: analisi + 4 immagini
  • chat                    — chat generica con GPT-4o
  • genera_immagine         — genera una singola immagine con gpt-image-1
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

# Percorsi ancorati alla cartella del progetto: il server MCP può essere
# lanciato da Claude Desktop con una working directory qualsiasi.
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

from services.image_service import generate_clothing_images
from services.openai_describe_service import analyze_clothing

mcp = FastMCP("arturo-openai")
GENERATED_DIR = BASE_DIR / "generated"
GENERATED_DIR.mkdir(exist_ok=True)


def _client() -> openai.OpenAI:
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise ValueError("OPENAI_API_KEY non impostata nel file .env")
    return openai.OpenAI(api_key=key)


def _require_key() -> str:
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise ValueError("OPENAI_API_KEY non impostata nel file .env")
    return key


# ---------------------------------------------------------------------------
# TOOL 1 — Analisi indumento con GPT-4o Vision
# ---------------------------------------------------------------------------
@mcp.tool()
def analizza_indumento(percorsi_immagini: list[str]) -> str:
    """
    Analizza le foto di un indumento e restituisce un JSON con titolo, categoria,
    genere, colori, materiale, taglia, brand, condizione, misure stimate,
    descrizioni per Vinted e Catawiki, hashtag, prezzo suggerito e prompt
    per gpt-image-1.

    Args:
        percorsi_immagini: Lista di percorsi file immagine (max 4).
                           Formati: JPG, PNG, WEBP.

    Returns:
        JSON string con tutti i campi dell'annuncio.
    """
    analisi = analyze_clothing(percorsi_immagini, _require_key())
    return json.dumps(analisi, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# TOOL 2 — Genera immagini moda con gpt-image-1
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
        JSON string con i percorsi dei file generati nella cartella 'generated/'
        e gli eventuali errori per immagine.
    """
    key = _require_key()

    if percorsi_riferimento:
        # Massima fedeltà: foto reali come riferimento
        filenames, errors = generate_clothing_images(
            reference_image_paths=percorsi_riferimento,
            model_prompt=prompt_modella,
            product_prompt=prompt_sfondo_bianco,
            api_key=key,
        )
        result = {k: str(GENERATED_DIR / f) for k, f in filenames.items()}
        if errors:
            result["errori"] = errors
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
    automaticamente le 4 immagini professionali con gpt-image-1.

    Args:
        percorsi_immagini: Lista di percorsi file immagine dell'indumento (max 4).

    Returns:
        JSON string con 'analisi' (tutti i dati dell'annuncio) e 'immagini' (percorsi file).
    """
    analisi = analyze_clothing(percorsi_immagini, _require_key())

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
