import os
import time
import uuid
import asyncio
import logging
from pathlib import Path
from typing import Optional
from functools import partial

from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from dotenv import load_dotenv

from services.openai_describe_service import analyze_clothing
from services.image_service import generate_clothing_images
from services.vinted_service import pubblica_su_vinted
from services.catawiki_service import pubblica_su_catawiki
from services.pw_runner import esegui

load_dotenv()

logger = logging.getLogger("arturo")

app = FastAPI(title="Arturo - Annunci Moda AI")

UPLOADS_DIR = Path("uploads")
GENERATED_DIR = Path("generated")
UPLOADS_DIR.mkdir(exist_ok=True)
GENERATED_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

# Su un server pubblico impostare REQUIRE_CLIENT_KEY=true: ogni utente deve
# fornire la propria chiave OpenAI e quella del server non viene mai usata.
REQUIRE_CLIENT_KEY = os.getenv("REQUIRE_CLIENT_KEY", "false").lower() == "true"

# Se impostata, le operazioni costose (analisi/pubblicazione) richiedono
# questa password: da usare quando l'app è esposta online.
APP_PASSWORD = os.getenv("APP_PASSWORD", "")
PROTECTED_PATHS = ("/api/analyze", "/api/publish")


@app.middleware("http")
async def check_app_password(request, call_next):
    if APP_PASSWORD and request.url.path.startswith(PROTECTED_PATHS):
        if request.headers.get("x-app-password", "") != APP_PASSWORD:
            return JSONResponse(
                {"detail": "Password dell'app errata o mancante"}, status_code=401
            )
    return await call_next(request)

GENERATED_MAX_AGE_DAYS = int(os.getenv("GENERATED_MAX_AGE_DAYS", "14"))


@app.on_event("startup")
async def cleanup_old_files():
    cutoff = time.time() - GENERATED_MAX_AGE_DAYS * 86400
    for folder in (GENERATED_DIR, UPLOADS_DIR):
        for f in folder.glob("*"):
            try:
                if f.is_file() and f.stat().st_mtime < cutoff:
                    f.unlink()
            except OSError:
                pass


def get_openai_key(form_key: Optional[str]) -> str:
    if REQUIRE_CLIENT_KEY:
        key = form_key or ""
        if not key:
            raise HTTPException(400, "Inserisci la tua API key OpenAI (richiesta su questo server)")
        return key
    key = form_key or os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise HTTPException(400, "API key OpenAI mancante")
    return key


@app.post("/api/analyze")
async def analyze(
    files: list[UploadFile] = File(...),
    openai_key: Optional[str] = Form(None),
):
    if not files:
        raise HTTPException(400, "Carica almeno una foto")
    if len(files) > 4:
        raise HTTPException(400, "Massimo 4 foto")

    oai_key = get_openai_key(openai_key)

    session_id = uuid.uuid4().hex
    saved_paths: list[str] = []

    def _cleanup():
        for p in saved_paths:
            Path(p).unlink(missing_ok=True)

    try:
        for upload in files:
            suffix = Path(upload.filename or "").suffix.lower()
            if suffix not in ALLOWED_EXTENSIONS:
                raise HTTPException(400, f"Formato non supportato: {suffix}. Usa JPG, PNG o WEBP.")
            content = await upload.read()
            if len(content) > MAX_FILE_SIZE:
                raise HTTPException(400, "File troppo grande (max 10 MB)")
            dest = UPLOADS_DIR / f"{session_id}_{uuid.uuid4().hex}{suffix}"
            dest.write_bytes(content)
            saved_paths.append(str(dest))

        loop = asyncio.get_running_loop()

        # Analisi GPT-4o su thread separato (non blocca il server)
        analysis = await loop.run_in_executor(
            None, analyze_clothing, saved_paths, oai_key
        )

        # Generazione 4 immagini in parallelo: TUTTE le foto originali come
        # riferimento visivo + descrizione GPT-4o nel prompt
        images = await loop.run_in_executor(
            None,
            partial(
                generate_clothing_images,
                reference_image_paths=saved_paths,
                model_prompt=analysis.get("prompt_immagine_modella", ""),
                product_prompt=analysis.get("prompt_sfondo_bianco", ""),
                api_key=oai_key,
            ),
        )
    except HTTPException:
        _cleanup()
        raise
    except Exception:
        _cleanup()
        logger.exception("Errore durante l'elaborazione dell'annuncio")
        raise HTTPException(500, "Errore durante l'elaborazione. Riprova; se persiste controlla i log del server.")

    _cleanup()
    return JSONResponse({"success": True, "analysis": analysis, "images": images})


@app.get("/api/image/{filename}")
async def get_image(filename: str):
    safe_name = Path(filename).name
    filepath = GENERATED_DIR / safe_name
    if not filepath.exists():
        raise HTTPException(404, "Immagine non trovata")
    return FileResponse(str(filepath), media_type="image/png")


@app.get("/api/download/{filename}")
async def download_image(filename: str):
    safe_name = Path(filename).name
    filepath = GENERATED_DIR / safe_name
    if not filepath.exists():
        raise HTTPException(404, "Immagine non trovata")
    return FileResponse(
        str(filepath),
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


class PublishRequest(BaseModel):
    analysis: dict
    image_filenames: list[str]


def _has_display() -> bool:
    # La pubblicazione apre un browser visibile: possibile solo dove c'è uno
    # schermo (PC dell'utente), non su un server remoto.
    return os.name == "nt" or bool(os.getenv("DISPLAY"))


async def _run_publish(publish_func, req: PublishRequest) -> dict:
    if not _has_display():
        raise HTTPException(
            400,
            "La pubblicazione automatica funziona solo con l'app installata sul tuo PC "
            "(apre una finestra del browser). Scarica e copia i testi e le immagini, "
            "oppure installa Arturo in locale.",
        )
    # Playwright gira su un loop dedicato (vedi services/pw_runner.py);
    # to_thread evita di bloccare il server durante login e compilazione.
    try:
        result = await asyncio.to_thread(
            esegui,
            publish_func(analysis=req.analysis, image_filenames=req.image_filenames),
        )
    except TimeoutError:
        raise HTTPException(500, "Tempo scaduto: la pubblicazione ha impiegato troppo. Riprova.")
    except Exception:
        logger.exception("Errore durante la pubblicazione")
        raise HTTPException(500, "Errore durante la pubblicazione: controlla i log del server.")
    if not result.get("success"):
        raise HTTPException(500, result.get("error", "Errore sconosciuto"))
    return result


@app.post("/api/publish/vinted")
async def publish_vinted(req: PublishRequest):
    return await _run_publish(pubblica_su_vinted, req)


@app.post("/api/publish/catawiki")
async def publish_catawiki(req: PublishRequest):
    return await _run_publish(pubblica_su_catawiki, req)


APP_VERSION = "1.3-catawiki-wizard"


@app.get("/health")
async def health():
    return {"status": "ok", "version": APP_VERSION}


@app.get("/api/config")
async def config():
    has_key = bool(os.getenv("OPENAI_API_KEY", "").strip()) and not REQUIRE_CLIENT_KEY
    return {
        "server_has_key": has_key,
        "password_required": bool(APP_PASSWORD),
        "publish_available": _has_display(),
    }


app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
