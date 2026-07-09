import os
import openai
import base64
import uuid
import io
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image


GENERATED_DIR = Path("generated")

# Lato massimo delle foto di riferimento inviate a gpt-image-1
MAX_REF_PX = 1536

# high = massima fedeltà all'indumento (default). Impostare IMAGE_QUALITY=medium
# per risparmiare (~1/3 del costo) accettando meno dettaglio.
IMAGE_QUALITY = os.getenv("IMAGE_QUALITY", "high")


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
    api_key: str, key: str, prompt: str, refs: list[bytes]
) -> tuple[str, str]:
    client = openai.OpenAI(api_key=api_key)
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
    filepath = GENERATED_DIR / filename
    filepath.write_bytes(base64.b64decode(response.data[0].b64_json))
    return key, filename


def generate_clothing_images(
    reference_image_paths: list[str],
    model_prompt: str,
    product_prompt: str,
    api_key: str,
) -> dict[str, str]:
    """
    Genera 4 immagini professionali in parallelo usando:
    - TUTTE le foto originali come riferimento visivo (images.edit, max 4)
    - input_fidelity="high" per mantenere l'indumento identico all'originale
    - La descrizione dettagliata di GPT-4o nel prompt testuale
    """
    refs = [_to_jpeg_bytes(p) for p in reference_image_paths[:4]]

    prompts = {
        "model_front":     _model_prompt(model_prompt, "front"),
        "model_lifestyle": _model_prompt(model_prompt, "lifestyle"),
        "product_flat":    _product_prompt(product_prompt, "flat"),
        "product_hanger":  _product_prompt(product_prompt, "hanger"),
    }

    result: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(_generate_single, api_key, key, prompt, refs): key
            for key, prompt in prompts.items()
        }
        for future in as_completed(futures):
            key, filename = future.result()
            result[key] = filename

    return result
