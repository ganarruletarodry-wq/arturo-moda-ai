import os
import uuid
import asyncio
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

load_dotenv()

app = FastAPI(title="Arturo - Annunci Moda AI")

UPLOADS_DIR = Path("uploads")
GENERATED_DIR = Path("generated")
UPLOADS_DIR.mkdir(exist_ok=True)
GENERATED_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def get_openai_key(form_key: Optional[str]) -> str:
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
    saved_paths = []
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

    loop = asyncio.get_event_loop()
    try:
        # Analisi GPT-4o su thread separato (non blocca il server)
        analysis = await loop.run_in_executor(
            None, analyze_clothing, saved_paths, oai_key
        )

        # Generazione 4 immagini in parallelo: foto originale + descrizione GPT-4o
        images = await loop.run_in_executor(
            None,
            partial(
                generate_clothing_images,
                reference_image_path=saved_paths[0],
                model_prompt=analysis.get("prompt_immagine_modella", ""),
                product_prompt=analysis.get("prompt_sfondo_bianco", ""),
                api_key=oai_key,
            ),
        )
    except Exception as e:
        for p in saved_paths:
            Path(p).unlink(missing_ok=True)
        raise HTTPException(500, f"Errore durante l'elaborazione: {str(e)}")

    for p in saved_paths:
        Path(p).unlink(missing_ok=True)

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
    email: str
    password: str


@app.post("/api/publish/vinted")
async def publish_vinted(req: PublishRequest):
    result = await pubblica_su_vinted(
        analysis=req.analysis,
        image_filenames=req.image_filenames,
        email=req.email,
        password=req.password,
    )
    if not result.get("success"):
        raise HTTPException(500, result.get("error", "Errore sconosciuto"))
    return result


@app.post("/api/publish/catawiki")
async def publish_catawiki(req: PublishRequest):
    result = await pubblica_su_catawiki(
        analysis=req.analysis,
        image_filenames=req.image_filenames,
        email=req.email,
        password=req.password,
    )
    if not result.get("success"):
        raise HTTPException(500, result.get("error", "Errore sconosciuto"))
    return result


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/config")
async def config():
    has_key = bool(os.getenv("OPENAI_API_KEY", "").strip())
    return {"server_has_key": has_key}


app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
