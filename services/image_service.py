import os
import openai
import base64
import uuid
import io
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from PIL import Image


logger = logging.getLogger("arturo.images")

# Ancorato alla cartella del progetto, non alla working directory:
# così funziona anche quando il processo è avviato da un'altra cartella
# (es. MCP server lanciato da Claude Desktop).
BASE_DIR = Path(__file__).resolve().parent.parent
GENERATED_DIR = BASE_DIR / "generated"
GENERATED_DIR.mkdir(exist_ok=True)

# Lato massimo delle foto di riferimento inviate a gpt-image-1
MAX_REF_PX = 1536

# high = massima fedeltà all'indumento (default). Impostare IMAGE_QUALITY=medium
# per risparmiare (~1/3 del costo) accettando meno dettaglio.
IMAGE_QUALITY = os.getenv("IMAGE_QUALITY", "high")

# Un tentativo extra per immagine: gli errori transitori dell'API sono comuni
# e rigenerare una sola immagine costa molto meno che rifare tutto l'annuncio.
MAX_ATTEMPTS = 2


def _to_jpeg_bytes(image_path: str) -> bytes:
    img = Image.open(image_path).convert("RGB")
    if max(img.size) > MAX_REF_PX:
        img.thumbnail((MAX_REF_PX, MAX_REF_PX), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


FIDELITY_RULES = (
    "STRICT RULES — this is a real second-hand garment being sold online, the photos "
    "must show the REAL item: keep the garment 100% IDENTICAL to the reference photos. "
    "Same exact color and shade, same fabric and texture, same pattern and print placement, "
    "same logos and lettering (reproduce them exactly, do not invent or alter text), "
    "same buttons, zippers, seams, pockets, collar and cuffs, same proportions and fit. "
    "Do NOT redesign, restyle, recolor, clean up or 'improve' the garment in any way. "
    "Only change the setting, lighting and presentation."
)


def _model_prompt(description: str, pose: str) -> str:
    pose_desc = (
        "front view, standing straight, full body visible" if pose == "front"
        else "three-quarter view, relaxed natural pose"
    )
    return (
        f"Professional fashion e-commerce photography. A model wearing the exact garment "
        f"shown in the reference photos: {description}. {pose_desc}. "
        f"Soft studio lighting, clean light-grey seamless background, sharp focus on the garment. "
        f"{FIDELITY_RULES}"
    )


def _product_prompt(description: str, style: str) -> str:
    layout = (
        "flat lay, shot from directly above, neatly arranged, wrinkles smoothed"
        if style == "flat"
        else "hanging on a wooden hanger against the wall, front view, perfectly straight"
    )
    return (
        f"Professional e-commerce product photography of the exact garment shown in the "
        f"reference photos: {description}. {layout}. "
        f"Pure white (#FFFFFF) background, bright even lighting, minimal soft shadow. "
        f"{FIDELITY_RULES}"
    )


def _generate_single(
    client: openai.OpenAI, key: str, prompt: str, refs: list[bytes]
) -> str:
    last_error: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            images = [
                (f"reference_{i}.jpg", io.BytesIO(data), "image/jpeg")
                for i, data in enumerate(refs)
            ]
            response = client.images.edit(
                model="gpt-image-1",
                image=images if len(images) > 1 else images[0],
                prompt=prompt,
                size="1024x1024",
                quality=IMAGE_QUALITY,
                input_fidelity="high",  # preserva colori, stampe, loghi e tessuto del capo
                n=1,
            )
            filename = f"{uuid.uuid4().hex}_{key}.png"
            (GENERATED_DIR / filename).write_bytes(
                base64.b64decode(response.data[0].b64_json)
            )
            return filename
        except Exception as e:
            last_error = e
            logger.warning("Immagine %s, tentativo %d fallito: %s", key, attempt + 1, e)
    raise last_error


def generate_clothing_images(
    reference_image_paths: list[str],
    model_prompt: str,
    product_prompt: str,
    api_key: str,
) -> tuple[dict[str, str], dict[str, str]]:
    """
    Genera 4 immagini professionali in parallelo usando:
    - TUTTE le foto originali come riferimento visivo (images.edit, max 4)
    - input_fidelity="high" per mantenere l'indumento identico all'originale
    - La descrizione dettagliata di GPT-4o nel prompt testuale

    Ogni immagine è indipendente: se una fallisce (dopo un retry) le altre
    vengono comunque restituite, così l'utente non perde ciò che ha già pagato.

    Returns:
        (immagini, errori): due dict chiave → nome file / chiave → messaggio errore.
    """
    refs = [_to_jpeg_bytes(p) for p in reference_image_paths[:4]]
    client = openai.OpenAI(api_key=api_key)  # thread-safe, condiviso dai worker

    prompts = {
        "model_front":     _model_prompt(model_prompt, "front"),
        "model_lifestyle": _model_prompt(model_prompt, "lifestyle"),
        "product_flat":    _product_prompt(product_prompt, "flat"),
        "product_hanger":  _product_prompt(product_prompt, "hanger"),
    }

    images: dict[str, str] = {}
    errors: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            key: executor.submit(_generate_single, client, key, prompt, refs)
            for key, prompt in prompts.items()
        }
        for key, future in futures.items():
            try:
                images[key] = future.result()
            except Exception as e:
                errors[key] = str(e)[:300]
                logger.error("Immagine %s non generata: %s", key, e)

    return images, errors
