import openai
import base64
import uuid
import io
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image


GENERATED_DIR = Path("generated")


def _to_png_bytes(image_path: str) -> bytes:
    """Converte l'immagine originale in PNG (richiesto da images.edit)."""
    img = Image.open(image_path).convert("RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _build_model_prompt(pose: str) -> str:
    if pose == "front":
        return (
            "Take this exact clothing item and show it being worn by a stylish fashion model. "
            "Full body, front view, standing straight. Professional studio lighting, "
            "clean neutral background. Keep the clothing 100% identical — same color, "
            "pattern, style, and details. High-end fashion magazine quality."
        )
    else:
        return (
            "Take this exact clothing item and show it being worn by a stylish fashion model. "
            "Three-quarter view, relaxed lifestyle pose. Natural lighting, urban or minimal background. "
            "Keep the clothing 100% identical — same color, pattern, style, and details. "
            "Editorial fashion photography quality."
        )


def _build_product_prompt(style: str) -> str:
    if style == "flat":
        return (
            "Take this exact clothing item and display it as a flat lay on a pure white background. "
            "Shot from directly above, perfectly arranged, no wrinkles. "
            "Bright even lighting, no shadows. Keep every detail identical — same color, "
            "pattern, fabric texture. Professional e-commerce product photography."
        )
    else:
        return (
            "Take this exact clothing item and display it hanging on an invisible hanger "
            "against a pure white background. Front view, perfectly straight. "
            "Bright even lighting, soft minimal shadow. Keep every detail identical — "
            "same color, pattern, fabric texture. Professional e-commerce product photography."
        )


def _generate_single(api_key: str, key: str, prompt: str, png_bytes: bytes) -> tuple[str, str]:
    """Genera una singola immagine usando l'indumento originale come riferimento."""
    client = openai.OpenAI(api_key=api_key)

    response = client.images.edit(
        model="gpt-image-1",
        image=("reference.png", io.BytesIO(png_bytes), "image/png"),
        prompt=prompt,
        size="1024x1024",
        n=1,
    )

    filename = f"{uuid.uuid4().hex}_{key}.png"
    filepath = GENERATED_DIR / filename
    filepath.write_bytes(base64.b64decode(response.data[0].b64_json))
    return key, filename


def generate_clothing_images(
    reference_image_path: str,
    api_key: str,
) -> dict[str, str]:
    """
    Genera 4 immagini professionali usando la foto originale dell'indumento come riferimento.
    Le 4 generazioni avvengono in parallelo.
    """
    png_bytes = _to_png_bytes(reference_image_path)

    prompts = {
        "model_front":     _build_model_prompt("front"),
        "model_lifestyle": _build_model_prompt("lifestyle"),
        "product_flat":    _build_product_prompt("flat"),
        "product_hanger":  _build_product_prompt("hanger"),
    }

    result: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(_generate_single, api_key, key, prompt, png_bytes): key
            for key, prompt in prompts.items()
        }
        for future in as_completed(futures):
            key, filename = future.result()
            result[key] = filename

    return result
