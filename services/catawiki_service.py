"""
Pubblicazione assistita su Catawiki tramite Playwright.

Apre un browser VISIBILE con profilo persistente: l'utente fa login la prima
volta (la sessione resta memorizzata), l'app precompila il lotto con tutti i
dati generati e si ferma. L'utente controlla e invia il lotto a mano.
Nota: su Catawiki i lotti passano comunque dall'approvazione degli esperti.
"""

import asyncio
import time
from pathlib import Path
from playwright.async_api import async_playwright


# Mappa condizioni Arturo → Catawiki
CONDIZIONE_MAP = {
    "Nuovo con etichetta": "New with tags",
    "Nuovo senza etichetta": "New without tags",
    "Ottimo": "Very good",
    "Buono": "Good",
    "Discreto": "Fair",
}

BASE_DIR = Path(__file__).resolve().parent.parent
PROFILE_DIR = BASE_DIR / "browser_profiles" / "catawiki"
LOGIN_TIMEOUT_S = 300  # 5 minuti per completare il login manuale

# Il browser resta aperto dopo la risposta HTTP: è l'utente a inviare il lotto.
# Viene chiuso automaticamente alla pubblicazione successiva.
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
        blocked = any(k in page.url for k in ("login", "signup", "auth"))
        if not blocked:
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


async def _continue(page) -> bool:
    """Clicca Continue/Next per passare allo step successivo del wizard."""
    try:
        await page.locator(
            'button:has-text("Continue"), button:has-text("Next"), button:has-text("Continua")'
        ).first.click(timeout=5000)
        await asyncio.sleep(2.5)
        return True
    except Exception:
        return False


async def pubblica_su_catawiki(
    analysis: dict,
    image_filenames: list[str],
) -> dict:
    generated_dir = BASE_DIR / "generated"
    image_paths = [
        str(generated_dir / f)
        for f in image_filenames
        if (generated_dir / f).exists()
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
    # Wizard venditori Catawiki: Object → Images → Details → Value → Shipping
    form_url = "https://www.catawiki.com/en/v/lot/new"
    url_marker = "v/lot/new"

    try:
        await page.goto(form_url, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        if url_marker not in page.url:
            if not await _wait_for_login(page, form_url, url_marker):
                return {
                    "success": False,
                    "error": "Login non completato entro 5 minuti. "
                             "Riprova: la prossima volta la sessione sarà memorizzata.",
                }
        await asyncio.sleep(2)

        # --- STEP 1: OBJECT — "What can we help you sell?" ---
        categoria = analysis.get("categoria", "")
        brand = analysis.get("brand", "")
        query = " ".join(x for x in (brand, categoria) if x).strip() or "Clothing"
        try:
            search = page.locator(
                'input[type="search"], input[placeholder*="sell" i], '
                'input[placeholder*="E.g" i], main input[type="text"]'
            ).first
            await search.fill(query, timeout=8000)
            await asyncio.sleep(2)
            # seleziona il primo suggerimento se compare
            try:
                sugg = page.locator('[role="option"], [role="listbox"] li').first
                if await sugg.is_visible(timeout=3000):
                    await sugg.click()
                    await asyncio.sleep(1)
            except Exception:
                pass
            compilati.append("Oggetto")
        except Exception:
            mancanti.append("Oggetto")

        await _continue(page)

        # --- STEP 2: IMAGES ---
        if image_paths:
            try:
                file_input = page.locator('input[type="file"]').first
                await file_input.set_input_files(image_paths[:4], timeout=15000)
                await asyncio.sleep(6)  # attesa upload
                compilati.append("Foto")
            except Exception:
                mancanti.append("Foto")
            await _continue(page)

        # --- STEP 3: DETAILS — titolo, descrizione, condizione, taglia ---
        await _try(
            "Titolo",
            page.locator(
                'input[name*="title" i], input[id*="title" i], input[placeholder*="title" i]'
            ).first.fill(analysis.get("titolo", ""), timeout=6000),
            compilati, mancanti,
        )

        desc = analysis.get("descrizione_catawiki", "")
        misure = analysis.get("misure", {})
        if misure:
            labels = {
                "petto_busto": "Petto/Busto", "spalle": "Spalle",
                "vita": "Vita", "fianchi": "Fianchi",
                "lunghezza_totale": "Lunghezza totale",
                "lunghezza_gamba": "Lunghezza gamba",
                "maniche": "Maniche",
            }
            lines = [
                f"• {label}: {misure[k]}"
                for k, label in labels.items()
                if misure.get(k) and misure.get(k) != "null"
            ]
            if lines:
                desc += "\n\nMisure:\n" + "\n".join(lines)

        await _try(
            "Descrizione",
            page.locator(
                'textarea[name*="desc" i], textarea[id*="desc" i], [contenteditable="true"], textarea'
            ).first.fill(desc, timeout=6000),
            compilati, mancanti,
        )

        condizione_cat = CONDIZIONE_MAP.get(analysis.get("condizione", "Buono"), "Good")
        await _try(
            "Condizione",
            page.locator(
                f'select[name*="condition" i], [role="option"]:has-text("{condizione_cat}"), '
                f'label:has-text("{condizione_cat}")'
            ).first.click(timeout=4000),
            compilati, mancanti,
        )

        taglia = analysis.get("taglia", "")
        if taglia:
            await _try(
                "Taglia",
                page.locator('input[name*="size" i], select[name*="size" i]')
                    .first.fill(taglia, timeout=3000),
                compilati, mancanti,
            )

        await _continue(page)

        # --- STEP 4: VALUE — prezzo di riserva / stima ---
        prezzo_min = analysis.get("prezzo_suggerito_min", 5)
        await _try(
            "Prezzo",
            page.locator(
                'input[name*="price" i], input[id*="price" i], '
                'input[name*="reserve" i], input[placeholder*="price" i], input[type="number"]'
            ).first.fill(str(prezzo_min), timeout=5000),
            compilati, mancanti,
        )

        # STOP: lo step Shipping e l'invio finale restano all'utente
        return {
            "success": True,
            "message": "Lotto precompilato su Catawiki! Completa la spedizione nella finestra "
                       "del browser, controlla i dati e invia tu il lotto.",
            "compilati": compilati,
            "mancanti": mancanti,
        }

    except Exception as e:
        return {"success": False, "error": str(e)[:500]}
