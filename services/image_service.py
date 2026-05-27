import openai
import base64
import uuid
from pathlib import Path


GENERATED_DIR = Path("generated")


def _build_model_prompt(base_prompt: str, pose: str) -> str:
    poses = {
        "front": "front view, standing straight, full body shot",
        "lifestyle": "three-quarter view, natural casual pose, lifestyle fashion photo",
    }
    return (
        f"Professional fashion photography. A stylish model wearing {base_prompt}. "
        f"{poses[pose]}. Studio lighting, clean neutral background, "
        f"high-end fashion magazine style, sharp focus, 4K quality. "
        f"The clothing is the main subject."
    )


def _build_product_prompt(base_prompt: str, style: str) -> str:
    if style == "flat":
        return (
            f"Professional product photography. {base_prompt}. "
            f"Flat lay on pure white background, perfectly arranged, "
            f"e-commerce style, bright even lighting, no shadows, "
            f"shot from directly above, fashion marketplace photo quality."
        )
    else:
        return (
            f"Professional product photography. {base_prompt}. "
            f"Displayed on invisible hanger on pure white background, "
            f"e-commerce style, bright even lighting, slight soft shadow, "
            f"front view, fashion marketplace photo quality."
        )


def generate_clothing_images(
    model_prompt: str,
    product_prompt: str,
    api_key: str,
) -> dict[str, str]:
    client = openai.OpenAI(api_key=api_key)

    prompts = {
        "model_front": _build_model_prompt(model_prompt, "front"),
        "model_lifestyle": _build_model_prompt(model_prompt, "lifestyle"),
        "product_flat": _build_product_prompt(product_prompt, "flat"),
        "product_hanger": _build_product_prompt(product_prompt, "hanger"),
    }

    result = {}
    for key, prompt in prompts.items():
        response = client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size="1024x1024",
            quality="high",
            n=1,
        )
        b64_data = response.data[0].b64_json

        filename = f"{uuid.uuid4().hex}_{key}.png"
        filepath = GENERATED_DIR / filename
        filepath.write_bytes(base64.b64decode(b64_data))

        result[key] = filename

    return result
