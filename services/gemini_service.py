"""
Analisi indumento e generazione immagini tramite Google Gemini.

- Analisi: gemini-3.5-flash (vision + JSON), costa pochi millesimi
- Immagini: gemini-3.1-flash-image ("Nano Banana 2"), ~€0.04 a immagine,
  con le foto reali del capo come riferimento per la massima fedeltà.

Stesse interfacce dei servizi OpenAI, così main.py può scambiare provider
con la variabile AI_PROVIDER.
"""

import os
import json
import time
import uuid
import base64
import logging
from concurrent.futures import ThreadPoolExecutor

import httpx

from services.image_service import (
    GENERATED_DIR,
    MAX_ATTEMPTS,
    _model_prompt,
    _product_prompt,
    _to_jpeg_bytes,
)
from services.openai_describe_service import SYSTEM_PROMPT, ANALYSIS_PROMPT, _encode_image

logger = logging.getLogger("arturo.gemini")

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-3.5-flash")
IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")


class GeminiQuotaError(Exception):
    """Quota/fatturazione esaurita (HTTP 429)."""


class GeminiAuthError(Exception):
    """Chiave non valida o senza permessi (HTTP 401/403)."""


def _post(model: str, payload: dict, api_key: str, timeout: float) -> dict:
    # I modelli Gemini rispondono a volte 500/503 sotto carico: si risolve
    # quasi sempre riprovando dopo qualche secondo.
    last_error: Exception | None = None
    for attempt in range(4):
        if attempt:
            time.sleep(2 * attempt)
        try:
            r = httpx.post(
                f"{GEMINI_BASE}/models/{model}:generateContent",
                headers={"x-goog-api-key": api_key},
                json=payload,
                timeout=timeout,
            )
        except httpx.HTTPError as e:
            last_error = e
            logger.warning("Gemini %s, errore di rete (tentativo %d): %s", model, attempt + 1, e)
            continue
        if r.status_code == 429:
            raise GeminiQuotaError(r.text[:400])
        if r.status_code in (401, 403):
            raise GeminiAuthError(r.text[:400])
        if r.status_code >= 500:
            last_error = httpx.HTTPStatusError(
                f"{r.status_code} da Gemini", request=r.request, response=r
            )
            logger.warning("Gemini %s, HTTP %d (tentativo %d)", model, r.status_code, attempt + 1)
            continue
        r.raise_for_status()
        return r.json()
    raise last_error


def _response_text(data: dict) -> str:
    # La risposta può arrivare divisa in più parti (e includere parti di
    # "ragionamento" da ignorare): vanno concatenate solo le parti di testo.
    parts = data["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts if not p.get("thought"))


def analyze_clothing_gemini(image_paths: list[str], api_key: str) -> dict:
    parts: list[dict] = []
    for path in image_paths[:4]:
        b64, mime = _encode_image(path)
        parts.append({"inline_data": {"mime_type": mime, "data": b64}})
    parts.append({"text": SYSTEM_PROMPT + "\n\n" + ANALYSIS_PROMPT})

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "maxOutputTokens": 8192,
        },
    }

    last_error: Exception | None = None
    for _ in range(2):
        data = _post(TEXT_MODEL, payload, api_key, timeout=120)
        try:
            return json.loads(_response_text(data))
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            last_error = e
    raise ValueError(f"Gemini non ha restituito un JSON valido: {last_error}")


def _generate_single_gemini(
    api_key: str, key: str, prompt: str, refs: list[bytes]
) -> str:
    parts = [
        {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(d).decode()}}
        for d in refs
    ]
    parts.append({"text": prompt})
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"imageConfig": {"aspectRatio": "1:1"}},
    }

    last_error: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            data = _post(IMAGE_MODEL, payload, api_key, timeout=180)
            image_parts = [
                p for p in data["candidates"][0]["content"]["parts"]
                if "inlineData" in p
            ]
            if not image_parts:
                raise ValueError("Nessuna immagine nella risposta di Gemini")
            filename = f"{uuid.uuid4().hex}_{key}.png"
            (GENERATED_DIR / filename).write_bytes(
                base64.b64decode(image_parts[0]["inlineData"]["data"])
            )
            return filename
        except (GeminiQuotaError, GeminiAuthError):
            raise  # inutile riprovare: quota o chiave
        except Exception as e:
            last_error = e
            logger.warning("Immagine %s, tentativo %d fallito: %s", key, attempt + 1, e)
    raise last_error


def generate_clothing_images_gemini(
    reference_image_paths: list[str],
    model_prompt: str,
    product_prompt: str,
    api_key: str,
) -> tuple[dict[str, str], dict[str, str]]:
    """
    Genera le 4 immagini in parallelo con Gemini usando le foto originali
    come riferimento. Stessa forma di ritorno del servizio OpenAI:
    (immagini, errori). Se la quota è esaurita l'errore viene propagato
    (non ha senso restituire risultati parziali: fallirebbero tutte).
    """
    refs = [_to_jpeg_bytes(p) for p in reference_image_paths[:4]]

    prompts = {
        "model_front":     _model_prompt(model_prompt, "front"),
        "model_lifestyle": _model_prompt(model_prompt, "lifestyle"),
        "product_flat":    _product_prompt(product_prompt, "flat"),
        "product_hanger":  _product_prompt(product_prompt, "hanger"),
    }

    images: dict[str, str] = {}
    errors: dict[str, str] = {}
    quota_error: GeminiQuotaError | None = None
    auth_error: GeminiAuthError | None = None

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            key: executor.submit(_generate_single_gemini, api_key, key, prompt, refs)
            for key, prompt in prompts.items()
        }
        for key, future in futures.items():
            try:
                images[key] = future.result()
            except GeminiQuotaError as e:
                quota_error = e
            except GeminiAuthError as e:
                auth_error = e
            except Exception as e:
                errors[key] = str(e)[:300]
                logger.error("Immagine %s non generata: %s", key, e)

    # Se non è uscita nemmeno un'immagine per quota/chiave, meglio l'errore
    # esplicito (l'utente deve sapere che va sistemata la fatturazione).
    if not images and quota_error:
        raise quota_error
    if not images and auth_error:
        raise auth_error
    if quota_error:
        errors["quota"] = "Quota Gemini esaurita durante la generazione"

    return images, errors
