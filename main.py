import os
import sys
import time
import uuid
import json
import asyncio
import logging
import secrets
import threading
from datetime import date, datetime, timezone
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from functools import partial

import openai
from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Request
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.gzip import GZipMiddleware
from dotenv import load_dotenv

# Percorsi ancorati alla cartella del progetto, non alla working directory
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

from services.openai_describe_service import analyze_clothing
from services.image_service import generate_clothing_images
from services.gemini_service import (
    analyze_clothing_gemini,
    generate_clothing_images_gemini,
    GeminiQuotaError,
    GeminiAuthError,
)
from services.vinted_service import pubblica_su_vinted
from services.catawiki_service import pubblica_su_catawiki
from services.pw_runner import esegui

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("arturo")

UPLOADS_DIR = BASE_DIR / "uploads"
GENERATED_DIR = BASE_DIR / "generated"
UPLOADS_DIR.mkdir(exist_ok=True)
GENERATED_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

# Su un server pubblico impostare REQUIRE_CLIENT_KEY=true: ogni utente deve
# fornire la propria chiave e quella del server non viene mai usata.
REQUIRE_CLIENT_KEY = os.getenv("REQUIRE_CLIENT_KEY", "false").lower() == "true"

# Provider AI: gemini (default se c'è GEMINI_API_KEY, ~€0.16/annuncio)
# oppure openai (~€0.80/annuncio). Forzabile con AI_PROVIDER.
AI_PROVIDER = os.getenv("AI_PROVIDER", "").lower() or (
    "gemini" if os.getenv("GEMINI_API_KEY") else "openai"
)
PROVIDER_KEY_ENV = {"gemini": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY"}

# Se impostata, le operazioni costose (analisi/pubblicazione) richiedono
# questa password: da usare quando l'app è esposta online.
APP_PASSWORD = os.getenv("APP_PASSWORD", "")
PROTECTED_PATHS = ("/api/analyze", "/api/publish", "/api/stats")

# Massimo di annunci generabili per IP ogni ora (protezione costi API).
# 0 = nessun limite. Ogni annuncio costa ~€0.80 di API OpenAI.
RATE_LIMIT_PER_HOUR = int(os.getenv("RATE_LIMIT_PER_HOUR", "12"))
_rate_windows: dict[str, deque] = defaultdict(deque)

GENERATED_MAX_AGE_DAYS = int(os.getenv("GENERATED_MAX_AGE_DAYS", "14"))
CLEANUP_INTERVAL_S = 6 * 3600  # pulizia file vecchi ogni 6 ore

# ---------------------------------------------------------------------------
# Statistiche uso (per il pannello di controllo): annunci, immagini, spesa
# stimata. Su Railway il filesystem è effimero: i contatori ripartono a ogni
# nuovo deploy — la data "da" nel pannello lo rende esplicito.
# ---------------------------------------------------------------------------
STATS_FILE = BASE_DIR / "stats.json"
_stats_lock = threading.Lock()

IMAGE_QUALITY = os.getenv("IMAGE_QUALITY", "high")
# Stime in EUR (vedi tabella costi in CLAUDE.md)
COST_PER_IMAGE_EUR = {"low": 0.03, "medium": 0.07, "high": 0.19}
COST_ANALYSIS_EUR = 0.02
# Gemini: Nano Banana 2 ($0.039/img a 1024px) + analisi flash
GEMINI_COST_PER_IMAGE_EUR = 0.036
GEMINI_COST_ANALYSIS_EUR = 0.005


def _cost_per_image() -> float:
    if AI_PROVIDER == "gemini":
        return GEMINI_COST_PER_IMAGE_EUR
    return COST_PER_IMAGE_EUR.get(IMAGE_QUALITY, 0.19)


def _cost_analysis() -> float:
    return GEMINI_COST_ANALYSIS_EUR if AI_PROVIDER == "gemini" else COST_ANALYSIS_EUR


def _empty_stats() -> dict:
    return {
        "da": date.today().isoformat(),
        "giorni": {},               # "YYYY-MM-DD" -> n. annunci
        "annunci_totali": 0,
        "immagini_totali": 0,
        "spesa_stimata_eur": 0.0,
        "credito_openai": "sconosciuto",  # ok | esaurito | sconosciuto
        "ultimo_annuncio": None,
    }


def _load_stats() -> dict:
    try:
        return {**_empty_stats(), **json.loads(STATS_FILE.read_text(encoding="utf-8"))}
    except Exception:
        return _empty_stats()


def _save_stats(stats: dict) -> None:
    try:
        STATS_FILE.write_text(json.dumps(stats, ensure_ascii=False), encoding="utf-8")
    except OSError:
        logger.warning("Impossibile salvare stats.json")


def _record_annuncio(n_images: int) -> None:
    with _stats_lock:
        stats = _load_stats()
        today = date.today().isoformat()
        stats["giorni"][today] = stats["giorni"].get(today, 0) + 1
        # tieni solo gli ultimi 30 giorni
        stats["giorni"] = dict(sorted(stats["giorni"].items())[-30:])
        stats["annunci_totali"] += 1
        stats["immagini_totali"] += n_images
        stats["spesa_stimata_eur"] += _cost_analysis() + n_images * _cost_per_image()
        stats["credito_openai"] = "ok"
        stats["ultimo_annuncio"] = datetime.now(timezone.utc).isoformat()
        _save_stats(stats)


def _record_credito_esaurito() -> None:
    with _stats_lock:
        stats = _load_stats()
        stats["credito_openai"] = "esaurito"
        _save_stats(stats)


def _cleanup_old_files() -> None:
    cutoff = time.time() - GENERATED_MAX_AGE_DAYS * 86400
    for folder in (GENERATED_DIR, UPLOADS_DIR):
        for f in folder.glob("*"):
            try:
                if f.is_file() and f.stat().st_mtime < cutoff:
                    f.unlink()
            except OSError:
                pass


async def _cleanup_loop() -> None:
    while True:
        _cleanup_old_files()
        await asyncio.sleep(CLEANUP_INTERVAL_S)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Provider AI attivo: %s", AI_PROVIDER)
    if os.getenv(PROVIDER_KEY_ENV[AI_PROVIDER]) and not REQUIRE_CLIENT_KEY and not APP_PASSWORD:
        logger.warning(
            "ATTENZIONE: il server ha la chiave API ma nessuna APP_PASSWORD. "
            "Se l'app è esposta online, chiunque può generare annunci a tue spese. "
            "Imposta APP_PASSWORD nel .env (o REQUIRE_CLIENT_KEY=true)."
        )
    cleanup_task = asyncio.create_task(_cleanup_loop())
    yield
    cleanup_task.cancel()


app = FastAPI(title="Arturo - Annunci Moda AI", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.middleware("http")
async def check_app_password(request, call_next):
    if APP_PASSWORD and request.url.path.startswith(PROTECTED_PATHS):
        provided = request.headers.get("x-app-password", "")
        if not secrets.compare_digest(provided, APP_PASSWORD):
            return JSONResponse(
                {"detail": "Password dell'app errata o mancante"}, status_code=401
            )
    return await call_next(request)


def _client_ip(request: Request) -> str:
    # Dietro un proxy (Railway, Render...) l'IP reale è nel primo X-Forwarded-For
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_rate_limit(request: Request) -> None:
    if RATE_LIMIT_PER_HOUR <= 0:
        return
    ip = _client_ip(request)
    now = time.monotonic()
    window = _rate_windows[ip]
    while window and now - window[0] > 3600:
        window.popleft()
    if len(window) >= RATE_LIMIT_PER_HOUR:
        raise HTTPException(
            429,
            "Hai raggiunto il limite di annunci per quest'ora. "
            "Riprova più tardi (il limite protegge dai costi API).",
        )
    window.append(now)


def get_ai_key(form_key: Optional[str]) -> str:
    env_var = PROVIDER_KEY_ENV[AI_PROVIDER]
    if REQUIRE_CLIENT_KEY:
        key = form_key or ""
        if not key:
            raise HTTPException(400, "Inserisci la tua API key (richiesta su questo server)")
        return key
    key = form_key or os.getenv(env_var, "")
    if not key:
        raise HTTPException(400, f"API key mancante ({env_var})")
    return key


@app.post("/api/analyze")
async def analyze(
    request: Request,
    files: list[UploadFile] = File(...),
    openai_key: Optional[str] = Form(None),
):
    if not files:
        raise HTTPException(400, "Carica almeno una foto")
    if len(files) > 4:
        raise HTTPException(400, "Massimo 4 foto")

    _check_rate_limit(request)
    ai_key = get_ai_key(openai_key)

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

        analyze_fn = analyze_clothing_gemini if AI_PROVIDER == "gemini" else analyze_clothing
        images_fn = (
            generate_clothing_images_gemini if AI_PROVIDER == "gemini"
            else generate_clothing_images
        )

        # Analisi vision su thread separato (non blocca il server)
        analysis = await loop.run_in_executor(
            None, analyze_fn, saved_paths, ai_key
        )

        # Generazione 4 immagini in parallelo: TUTTE le foto originali come
        # riferimento visivo + descrizione dell'analisi nel prompt
        images, image_errors = await loop.run_in_executor(
            None,
            partial(
                images_fn,
                reference_image_paths=saved_paths,
                model_prompt=analysis.get("prompt_immagine_modella", ""),
                product_prompt=analysis.get("prompt_sfondo_bianco", ""),
                api_key=ai_key,
            ),
        )
    except HTTPException:
        _cleanup()
        raise
    except GeminiAuthError:
        _cleanup()
        raise HTTPException(401, "Chiave Gemini non valida o senza permessi. Controlla la API key.")
    except GeminiQuotaError:
        _cleanup()
        _record_credito_esaurito()
        raise HTTPException(
            402,
            "Quota Google Gemini esaurita o fatturazione non attiva: chi gestisce l'app "
            "deve controllare su console.cloud.google.com/billing. Se la fatturazione è "
            "appena stata attivata, riprova tra qualche minuto.",
        )
    except openai.AuthenticationError:
        _cleanup()
        raise HTTPException(401, "Chiave OpenAI non valida o revocata. Controlla la API key.")
    except openai.RateLimitError as e:
        _cleanup()
        if "insufficient_quota" in str(e):
            _record_credito_esaurito()
            raise HTTPException(
                402,
                "Credito OpenAI esaurito: chi gestisce l'app deve ricaricare su "
                "platform.openai.com → Settings → Billing.",
            )
        raise HTTPException(429, "OpenAI è al limite di richieste: riprova tra qualche minuto.")
    except Exception:
        _cleanup()
        logger.exception("Errore durante l'elaborazione dell'annuncio")
        raise HTTPException(500, "Errore durante l'elaborazione. Riprova; se persiste controlla i log del server.")

    _cleanup()
    _record_annuncio(len(images))

    if not images:
        # Analisi ok ma nessuna immagine: restituiamo comunque i testi,
        # che da soli valgono già l'annuncio.
        logger.error("Nessuna immagine generata: %s", image_errors)

    return JSONResponse({
        "success": True,
        "analysis": analysis,
        "images": images,
        "image_errors": image_errors,
    })


# I nomi file sono UUID univoci: il contenuto non cambia mai → cache lunga
IMAGE_CACHE_HEADERS = {"Cache-Control": "public, max-age=86400, immutable"}


@app.get("/api/image/{filename}")
async def get_image(filename: str):
    safe_name = Path(filename).name
    filepath = GENERATED_DIR / safe_name
    if not filepath.exists():
        raise HTTPException(404, "Immagine non trovata")
    return FileResponse(str(filepath), media_type="image/png", headers=IMAGE_CACHE_HEADERS)


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
    if os.getenv("PLAYWRIGHT_HEADLESS", "").lower() == "true":
        return False
    return os.name == "nt" or sys.platform == "darwin" or bool(os.getenv("DISPLAY"))


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


APP_VERSION = "1.6-gemini"


@app.get("/health")
async def health():
    return {"status": "ok", "version": APP_VERSION}


@app.get("/api/stats")
async def get_stats():
    stats = _load_stats()
    today = date.today().isoformat()
    railway_project = os.getenv("RAILWAY_PROJECT_ID", "")
    return {
        "annunci_oggi": stats["giorni"].get(today, 0),
        "annunci_30gg": sum(stats["giorni"].values()),
        "annunci_totali": stats["annunci_totali"],
        "immagini_totali": stats["immagini_totali"],
        "spesa_stimata_eur": round(stats["spesa_stimata_eur"], 2),
        "credito_openai": stats["credito_openai"],
        "ultimo_annuncio": stats["ultimo_annuncio"],
        "da": stats["da"],
        "provider": AI_PROVIDER,
        "qualita_immagini": IMAGE_QUALITY,
        "costo_annuncio_eur": round(_cost_analysis() + 4 * _cost_per_image(), 2),
        "rate_limit_ora": RATE_LIMIT_PER_HOUR,
        "versione": APP_VERSION,
        "railway_url": (
            f"https://railway.com/project/{railway_project}" if railway_project else None
        ),
    }


@app.get("/api/config")
async def config():
    has_key = (
        bool(os.getenv(PROVIDER_KEY_ENV[AI_PROVIDER], "").strip())
        and not REQUIRE_CLIENT_KEY
    )
    return {
        "server_has_key": has_key,
        "provider": AI_PROVIDER,
        "password_required": bool(APP_PASSWORD),
        "publish_available": _has_display(),
    }


app.mount("/", StaticFiles(directory=str(BASE_DIR / "frontend"), html=True), name="frontend")
