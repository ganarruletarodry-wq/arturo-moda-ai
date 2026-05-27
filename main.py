import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from dotenv import load_dotenv

from services.openai_describe_service import analyze_clothing
from services.image_service import generate_clothing_images

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

    try:
        analysis = analyze_clothing(saved_paths, oai_key)
        images = generate_clothing_images(
            model_prompt=analysis.get("prompt_immagine_modella", ""),
            product_prompt=analysis.get("prompt_sfondo_bianco", ""),
            api_key=oai_key,
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


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/config")
async def config():
    """Dice al frontend se la API key è già configurata nel .env del server."""
    has_key = bool(os.getenv("OPENAI_API_KEY", "").strip())
    return {"server_has_key": has_key}


app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
