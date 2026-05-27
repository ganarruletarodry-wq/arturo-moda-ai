import openai
import base64
import uuid
import io
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image


GENERATED_DIR = Path("generated")


def _to_png_bytes(image_path: str) -> bytes:
    img = Image.open(image_path).convert("RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _model_prompt(description: str, pose: str) -> str:
    pose_desc = (
        "front view, standing straight, full body" if pose == "front"
        else "three-quarter view, relaxed natural pose"
    )
    return (
        f"Fashion photography. A model wearing the EXACT clothing item from the reference image: {description}. "
        f"{pose_desc}. Studio lighting, clean neutral background. "
        f"CRITICAL: reproduce every single detail of the clothing exactly — "
        f"same color, same pattern, same cut, same texture, same print. "
        f"Do NOT redesign or modify the clothing in any way. Only add the model and background."
    )


def _product_prompt(description: str, style: str) -> str:
    layout = (
        "flat lay, shot from directly above, perfectly arranged"
        if style == "flat"
        else "hanging on an invisible hanger, front view, perfectly straight"
    )
    return (
        f"Professional e-commerce product photography. "
        f"The EXACT clothing item from the reference image: {description}. "
        f"{layout}. Pure white (#FFFFFF) background, bright even lighting, no shadows. "
        f"CRITICAL: reproduce every single detail exactly — "
        f"same color, same pattern, same cut, same texture, same print. "
        f"Do NOT redesign or modify the clothing in any way."
    )


def _generate_single(
    api_key: str, key: str, prompt: str, png_bytes: bytes
) -> tuple[str, str]:
    client = openai.OpenAI(api_key=api_key)
    response = client.images.edit(
        model="gpt-image-1",
        image=("reference.png", io.BytesIO(png_bytes), "image/png"),
        prompt=prompt,
        size="1024x1024",
        quality="medium",   # più veloce di high, qualità comunque ottima
        n=1,
    )
    filename = f"{uuid.uuid4().hex}_{key}.png"
    filepath = GENERATED_DIR / filename
    filepath.write_bytes(base64.b64decode(response.data[0].b64_json))
    return key, filename


def generate_clothing_images(
    reference_image_path: str,
    model_prompt: str,
    product_prompt: str,
    api_key: str,
) -> dict[str, str]:
    """
    Genera 4 immagini professionali in parallelo usando:
    - La foto originale come riferimento visivo (images.edit)
    - La descrizione dettagliata di GPT-4o nel prompt testuale
    """
    png_bytes = _to_png_bytes(reference_image_path)

    prompts = {
        "model_front":     _model_prompt(model_prompt, "front"),
        "model_lifestyle": _model_prompt(model_prompt, "lifestyle"),
        "product_flat":    _product_prompt(product_prompt, "flat"),
        "product_hanger":  _product_prompt(product_prompt, "hanger"),
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
