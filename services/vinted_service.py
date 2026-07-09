"""
Pubblicazione assistita su Vinted tramite Playwright.

Apre un browser VISIBILE con profilo persistente: l'utente fa login la prima
volta (la sessione resta memorizzata per le volte successive), l'app precompila
l'annuncio con tutti i dati generati — foto, titolo, descrizione, brand, taglia,
condizione, prezzo — e si ferma. L'utente controlla e clicca "Pubblica" a mano.
"""

import asyncio
import time
from pathlib import Path
from playwright.async_api import async_playwright


# Mappa condizioni Arturo → Vinted
CONDIZIONE_MAP = {
    "Nuovo con etichetta": "new_with_tags",
    "Nuovo senza etichetta": "new_without_tags",
    "Ottimo": "excellent",
    "Buono": "good",
    "Discreto": "satisfactory",
}

PROFILE_DIR = Path("browser_profiles") / "vinted"
LOGIN_TIMEOUT_S = 300  # 5 minuti per completare il login manuale

# Il browser resta aperto dopo la risposta HTTP: è l'utente a cliccare
# "Pubblica". Viene chiuso automaticamente alla pubblicazione successiva.
_session: dict = {"pw": None, "context": None}


async def _close_previous():
    ctx, pw = _session.get("context"), _session.get("pw")
    _session["context"] = _session["pw"] = None
    for closer in (ctx and ctx.close, pw and pw.stop):
        if closer:
            try:
                await closer()
            except Exception:
                pass


async def _wait_for_login(page, form_url: str, url_marker: str) -> bool:
    """Attende che l'utente completi il login manualmente, poi riapre il form."""
    deadline = time.monotonic() + LOGIN_TIMEOUT_S
    while time.monotonic() < deadline:
        if url_marker in page.url:
            return True
        blocked = any(k in page.url for k in ("login", "signup", "auth", "member"))
        if not blocked:
            # login completato (siamo su una pagina normale) → riapri il form
            try:
                await page.goto(form_url, wait_until="domcontentloaded")
            except Exception:
                pass
        await asyncio.sleep(3)
    return url_marker in page.url


async def _try(label: str, coro, compilati: list, mancanti: list):
    try:
        await coro
        compilati.append(label)
    except Exception:
        mancanti.append(label)


async def pubblica_su_vinted(
    analysis: dict,
    image_filenames: list[str],
    email: str = "",
    password: str = "",
    generated_dir: str = "generated",
) -> dict:
    image_paths = [
        str(Path(generated_dir) / f)
        for f in image_filenames
        if (Path(generated_dir) / f).exists()
    ]

    await _close_previous()
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    pw = await async_playwright().start()
    launch_kwargs = dict(
        user_data_dir=str(PROFILE_DIR),
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
        viewport={"width": 1280, "height": 900},
        locale="it-IT",
    )
    try:
        # Usa il vero Google Chrome installato (il login Google lo accetta);
        # se non c'è, ripiega sul Chromium di Playwright.
        try:
            context = await pw.chromium.launch_persistent_context(
                channel="chrome", **launch_kwargs
            )
        except Exception:
            context = await pw.chromium.launch_persistent_context(**launch_kwargs)
    except Exception as e:
        await pw.stop()
        return {"success": False, "error": f"Impossibile aprire il browser: {str(e)[:200]}"}

    _session["pw"] = pw
    _session["context"] = context
    page = context.pages[0] if context.pages else await context.new_page()

    compilati: list[str] = []
    mancanti: list[str] = []
    form_url = "https://www.vinted.it/items/new"

    try:
        await page.goto(form_url, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        if "items/new" not in page.url:
            # Non loggato: l'utente fa login nella finestra aperta
            if not await _wait_for_login(page, form_url, "items/new"):
                return {
                    "success": False,
                    "error": "Login non completato entro 5 minuti. "
                             "Riprova: la prossima volta la sessione sarà memorizzata.",
                }
        await asyncio.sleep(2)

        # --- FOTO ---
        if image_paths:
            await _try(
                "Foto",
                page.locator('input[type="file"]').first.set_input_files(image_paths[:4]),
                compilati, mancanti,
            )
            await asyncio.sleep(3)

        # --- TITOLO ---
        await _try(
            "Titolo",
            page.locator('input[id*="title"], input[name="title"], textarea[name="title"]')
                .first.fill(analysis.get("titolo", ""), timeout=5000),
            compilati, mancanti,
        )

        # --- DESCRIZIONE (con misure) ---
        desc = analysis.get("descrizione_vinted", "")
        misure = analysis.get("misure", {})
        if misure:
            labels = {
                "petto_busto": "Petto/Busto", "spalle": "Spalle",
                "vita": "Vita", "fianchi": "Fianchi",
                "lunghezza_totale": "Lunghezza", "maniche": "Maniche",
            }
            lines = [
                f"• {label}: {misure[k]}"
                for k, label in labels.items()
                if misure.get(k) and misure.get(k) != "null"
            ]
            if lines:
                desc += "\n\n📏 Misure:\n" + "\n".join(lines)

        await _try(
            "Descrizione",
            page.locator('textarea[name="description"], textarea[id*="desc"]')
                .first.fill(desc, timeout=5000),
            compilati, mancanti,
        )

        # --- BRAND ---
        brand = analysis.get("brand", "")
        if brand:
            try:
                brand_field = page.locator('input[name="brand"], input[id*="brand"]').first
                await brand_field.fill(brand, timeout=3000)
                await asyncio.sleep(1)
                suggestion = page.locator('[role="option"], [class*="suggestion"]').first
                if await suggestion.is_visible(timeout=2000):
                    await suggestion.click()
                compilati.append("Brand")
            except Exception:
                mancanti.append("Brand")

        # --- TAGLIA ---
        taglia = analysis.get("taglia", "")
        if taglia:
            try:
                size_btn = page.locator('button:has-text("Taglia"), [id*="size"]').first
                await size_btn.click(timeout=3000)
                size_option = page.locator(
                    f'[role="option"]:has-text("{taglia}"), li:has-text("{taglia}")'
                ).first
                await size_option.click(timeout=3000)
                compilati.append("Taglia")
            except Exception:
                mancanti.append("Taglia")

        # --- CONDIZIONE ---
        condizione_vinted = CONDIZIONE_MAP.get(analysis.get("condizione", "Buono"), "good")
        await _try(
            "Condizione",
            page.locator(
                f'[value="{condizione_vinted}"], input[name*="condition"][value*="{condizione_vinted}"]'
            ).first.click(timeout=3000),
            compilati, mancanti,
        )

        # --- PREZZO ---
        prezzo = analysis.get("prezzo_suggerito_max", 10)
        await _try(
            "Prezzo",
            page.locator('input[name="price"], input[id*="price"]')
                .first.fill(str(prezzo), timeout=3000),
            compilati, mancanti,
        )

        # STOP: niente click su "Pubblica" — il controllo finale spetta all'utente
        return {
            "success": True,
            "message": "Annuncio precompilato su Vinted! Controlla la finestra del browser, "
                       "correggi ciò che vuoi e clicca tu \"Pubblica\".",
            "compilati": compilati,
            "mancanti": mancanti,
        }

    except Exception as e:
        return {"success": False, "error": str(e)[:500]}
