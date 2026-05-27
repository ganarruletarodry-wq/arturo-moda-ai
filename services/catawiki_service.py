"""
Automazione Catawiki tramite Playwright.
Pubblica un lotto su catawiki.com con tutti i dati dell'analisi.
"""

import asyncio
import os
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout


HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "false").lower() == "true"

# Mappa condizioni Arturo → Catawiki
CONDIZIONE_MAP = {
    "Nuovo con etichetta": "New with tags",
    "Nuovo senza etichetta": "New without tags",
    "Ottimo": "Very good",
    "Buono": "Good",
    "Discreto": "Fair",
}


async def pubblica_su_catawiki(
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
            viewport={"width": 1280, "height": 900},
            locale="it-IT",
        )
        page = await context.new_page()

        try:
            # --- LOGIN ---
            await page.goto("https://www.catawiki.com/login", wait_until="domcontentloaded")
            await asyncio.sleep(2)

            await page.locator('input[name="email"], input[type="email"]').first.fill(email)
            await page.locator('input[name="password"], input[type="password"]').first.fill(password)
            await page.locator('button[type="submit"], input[type="submit"]').first.click()
            await page.wait_for_load_state("networkidle", timeout=15000)
            await asyncio.sleep(2)

            if "login" in page.url:
                raise Exception("Login fallito — controlla email e password.")

            # --- NUOVO LOTTO ---
            await page.goto("https://www.catawiki.com/en/lots/new", wait_until="domcontentloaded")
            await asyncio.sleep(2)

            # Catawiki chiede prima la categoria — cerca "Fashion" o abbigliamento
            categoria = analysis.get("categoria", "")
            try:
                cat_search = page.locator('input[placeholder*="category"], input[placeholder*="categor"]').first
                await cat_search.fill(categoria, timeout=5000)
                await asyncio.sleep(1)
                cat_option = page.locator(f'[role="option"]:has-text("{categoria}"), li:has-text("{categoria}")').first
                await cat_option.click(timeout=3000)
            except Exception:
                # Prova a cercare "Fashion" come fallback
                try:
                    cat_search = page.locator('input[placeholder*="category"]').first
                    await cat_search.fill("Fashion", timeout=3000)
                    await asyncio.sleep(1)
                    await page.locator('[role="option"]:has-text("Fashion")').first.click(timeout=3000)
                except Exception:
                    pass

            await asyncio.sleep(1)

            # Titolo / Nome del lotto
            await page.locator(
                'input[name="title"], input[id*="title"], input[placeholder*="title"], input[placeholder*="titolo"]'
            ).first.fill(analysis.get("titolo", ""), timeout=5000)

            # Descrizione con misure
            desc = analysis.get("descrizione_catawiki", "")
            misure = analysis.get("misure", {})
            if misure:
                lines = ["\n\nMisure:"]
                labels = {
                    "petto_busto": "Petto/Busto", "spalle": "Spalle",
                    "vita": "Vita", "fianchi": "Fianchi",
                    "lunghezza_totale": "Lunghezza totale",
                    "lunghezza_gamba": "Lunghezza gamba",
                    "maniche": "Maniche",
                }
                for k, label in labels.items():
                    v = misure.get(k)
                    if v and v != "null":
                        lines.append(f"• {label}: {v}")
                desc += "\n".join(lines)

            await page.locator(
                'textarea[name="description"], textarea[id*="desc"], [contenteditable="true"]'
            ).first.fill(desc, timeout=5000)

            # Condizione
            condizione_raw = analysis.get("condizione", "Buono")
            condizione_cat = CONDIZIONE_MAP.get(condizione_raw, "Good")
            try:
                cond_select = page.locator(
                    f'select[name*="condition"], [role="option"]:has-text("{condizione_cat}")'
                ).first
                await cond_select.click(timeout=3000)
            except Exception:
                pass

            # Prezzo di riserva (minimo)
            prezzo_min = analysis.get("prezzo_suggerito_min", 5)
            try:
                price_field = page.locator('input[name*="price"], input[id*="price"], input[placeholder*="price"]').first
                await price_field.fill(str(prezzo_min), timeout=3000)
            except Exception:
                pass

            # Upload foto
            if image_paths:
                try:
                    file_input = page.locator('input[type="file"]').first
                    await file_input.set_input_files(image_paths[:4], timeout=10000)
                    await asyncio.sleep(3)
                except Exception:
                    pass

            # Brand
            brand = analysis.get("brand", "")
            if brand:
                try:
                    brand_field = page.locator('input[name*="brand"], input[placeholder*="brand"]').first
                    await brand_field.fill(brand, timeout=3000)
                except Exception:
                    pass

            # Taglia
            taglia = analysis.get("taglia", "")
            if taglia:
                try:
                    size_field = page.locator('input[name*="size"], select[name*="size"]').first
                    await size_field.fill(taglia, timeout=3000)
                except Exception:
                    pass

            # Submit / Salva bozza
            await asyncio.sleep(1)
            submit_btn = page.locator(
                'button:has-text("Submit"), button:has-text("Save"), button:has-text("Next"), button[type="submit"]'
            ).last
            await submit_btn.click()
            await page.wait_for_load_state("networkidle", timeout=20000)
            await asyncio.sleep(2)

            url_lotto = page.url
            return {
                "success": True,
                "url": url_lotto,
                "message": "Lotto inviato su Catawiki!",
            }

        except PlaywrightTimeout as e:
            return {"success": False, "error": f"Timeout — elemento non trovato: {str(e)[:200]}"}
        except Exception as e:
            return {"success": False, "error": str(e)[:500]}
        finally:
            await browser.close()
