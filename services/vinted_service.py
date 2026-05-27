"""
Automazione Vinted tramite Playwright.
Publica un annuncio su vinted.it con tutti i dati dell'analisi.
"""

import asyncio
import os
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout


# Mappa condizioni Arturo → Vinted
CONDIZIONE_MAP = {
    "Nuovo con etichetta": "new_with_tags",
    "Nuovo senza etichetta": "new_without_tags",
    "Ottimo": "excellent",
    "Buono": "good",
    "Discreto": "satisfactory",
}

HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "false").lower() == "true"


async def pubblica_su_vinted(
    analysis: dict,
    image_filenames: list[str],
    email: str,
    password: str,
    generated_dir: str = "generated",
) -> dict:
    image_paths = [
        str(Path(generated_dir) / f)
        for f in image_filenames
        if (Path(generated_dir) / f).exists()
    ]

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=HEADLESS,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="it-IT",
        )
        page = await context.new_page()

        try:
            # --- LOGIN ---
            await page.goto("https://www.vinted.it", wait_until="domcontentloaded")
            await asyncio.sleep(2)

            # Cerca e clicca login
            login_btn = page.locator('a[href*="login"], button:has-text("Accedi"), a:has-text("Accedi")').first
            await login_btn.click()
            await page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(1)

            # Compila email e password
            await page.locator('input[name="username"], input[type="email"], input[id*="username"]').first.fill(email)
            await page.locator('input[name="password"], input[type="password"]').first.fill(password)
            await page.locator('button[type="submit"], input[type="submit"]').first.click()
            await page.wait_for_load_state("networkidle", timeout=15000)
            await asyncio.sleep(2)

            # Verifica login riuscito
            if "login" in page.url or "auth" in page.url:
                raise Exception("Login fallito — controlla email e password.")

            # --- NUOVA INSERZIONE ---
            await page.goto("https://www.vinted.it/items/new", wait_until="domcontentloaded")
            await asyncio.sleep(2)

            # Upload foto (max 20, usiamo le generate)
            file_input = page.locator('input[type="file"]').first
            if image_paths:
                await file_input.set_input_files(image_paths[:4])
                await asyncio.sleep(3)

            # Titolo
            await page.locator('input[id*="title"], input[name="title"], textarea[name="title"]').first.fill(
                analysis.get("titolo", "")
            )

            # Descrizione
            desc = analysis.get("descrizione_vinted", "")
            misure = analysis.get("misure", {})
            if misure:
                lines = ["\n📏 Misure:"]
                labels = {
                    "petto_busto": "Petto/Busto", "spalle": "Spalle",
                    "vita": "Vita", "fianchi": "Fianchi",
                    "lunghezza_totale": "Lunghezza", "maniche": "Maniche",
                }
                for k, label in labels.items():
                    v = misure.get(k)
                    if v and v != "null":
                        lines.append(f"• {label}: {v}")
                desc += "\n".join(lines)

            desc_field = page.locator('textarea[name="description"], textarea[id*="desc"]').first
            await desc_field.fill(desc)

            # Marca/Brand
            brand = analysis.get("brand", "")
            if brand:
                brand_field = page.locator('input[name="brand"], input[id*="brand"]').first
                try:
                    await brand_field.fill(brand, timeout=3000)
                    await asyncio.sleep(1)
                    # Seleziona prima opzione nel dropdown se appare
                    suggestion = page.locator('[role="option"], [class*="suggestion"]').first
                    if await suggestion.is_visible(timeout=2000):
                        await suggestion.click()
                except Exception:
                    pass

            # Taglia
            taglia = analysis.get("taglia", "")
            if taglia:
                try:
                    size_btn = page.locator('button:has-text("Taglia"), [id*="size"]').first
                    await size_btn.click(timeout=3000)
                    size_option = page.locator(f'[role="option"]:has-text("{taglia}"), li:has-text("{taglia}")').first
                    await size_option.click(timeout=3000)
                except Exception:
                    pass

            # Condizione
            condizione_raw = analysis.get("condizione", "Buono")
            condizione_vinted = CONDIZIONE_MAP.get(condizione_raw, "good")
            try:
                cond_btn = page.locator(f'[value="{condizione_vinted}"], input[name*="condition"][value*="{condizione_vinted}"]').first
                await cond_btn.click(timeout=3000)
            except Exception:
                pass

            # Prezzo
            prezzo = analysis.get("prezzo_suggerito_max", 10)
            try:
                price_field = page.locator('input[name="price"], input[id*="price"]').first
                await price_field.fill(str(prezzo), timeout=3000)
            except Exception:
                pass

            # Pubblica
            await asyncio.sleep(1)
            publish_btn = page.locator(
                'button:has-text("Pubblica"), button:has-text("Inserisci"), button[type="submit"]'
            ).last
            await publish_btn.click()
            await page.wait_for_load_state("networkidle", timeout=20000)
            await asyncio.sleep(2)

            url_annuncio = page.url
            return {
                "success": True,
                "url": url_annuncio,
                "message": "Annuncio pubblicato su Vinted!",
            }

        except PlaywrightTimeout as e:
            return {"success": False, "error": f"Timeout — elemento non trovato: {str(e)[:200]}"}
        except Exception as e:
            return {"success": False, "error": str(e)[:500]}
        finally:
            await browser.close()
