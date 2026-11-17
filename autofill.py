"""Fill common application form fields and attach a local resume, then stop."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
PRIVATE = ROOT / "data" / "private"


def fill_first(page, selectors: list[str], value: str, label: str) -> bool:
    if not value:
        return False
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() and locator.is_visible() and locator.is_enabled():
                locator.fill(value, timeout=1200)
                print(f"Rellenado: {label}")
                return True
        except PlaywrightError:
            continue
    print(f"Pendiente manual: no se reconoció el campo {label}.")
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--job-id")
    selection.add_argument("--all-queued", action="store_true")
    args = parser.parse_args()
    profile_path, jobs_path = PRIVATE / "profile.json", PRIVATE / "jobs.json"
    if not profile_path.exists() or not jobs_path.exists():
        parser.error("Guarda primero tu perfil y al menos una oferta desde el panel local.")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    jobs = json.loads(jobs_path.read_text(encoding="utf-8"))
    if args.all_queued:
        selected = [item for item in jobs if item.get("status") == "queued" and
                    item.get("application_url", "").startswith(("https://", "http://"))]
    else:
        selected = [item for item in jobs if item["id"] == args.job_id and
                    item.get("application_url", "").startswith(("https://", "http://"))]
    if not selected:
        parser.error("No hay oferta seleccionada con una URL http(s) válida.")
    resume = PRIVATE / Path(profile.get("resume_file", "")).name
    if not resume.is_file():
        parser.error("No se encontró el CV local.")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(accept_downloads=False)
        for number, job in enumerate(selected, start=1):
            print(f"\n[{number}/{len(selected)}] {job['company']} | {job['title']}")
            print("Se abrirá el sitio indicado por ti. Verifica su autenticidad y política de privacidad.")
            page = context.new_page()
            try:
                page.goto(job["application_url"], wait_until="domcontentloaded", timeout=30000)
                if page.locator("iframe[title*='captcha' i], [data-sitekey], input[name*='captcha' i]").count():
                    print("Se detectó un CAPTCHA o control anti-bot. No se intenta resolver; continúa manualmente.")
                else:
                    fill_first(page, ['input[type="email"]', 'input[name*="email" i]', 'input[id*="email" i]'],
                               profile.get("email", ""), "correo")
                    fill_first(page, ['input[type="tel"]', 'input[name*="phone" i]', 'input[id*="phone" i]'],
                               profile.get("phone", ""), "teléfono")
                    fill_first(page, ['input[name*="full_name" i]', 'input[name="name" i]', 'input[id*="name" i]'],
                               profile.get("full_name", ""), "nombre")
                    fill_first(page, ['input[name*="location" i]', 'input[id*="location" i]'],
                               profile.get("location", ""), "ubicación")
                    fill_first(page, ['input[name*="linkedin" i]', 'input[id*="linkedin" i]'],
                               profile.get("linkedin", ""), "LinkedIn")
                    fill_first(page, ['input[name*="portfolio" i]', 'input[id*="portfolio" i]'],
                               profile.get("portfolio", ""), "portafolio")
                    try:
                        files = page.locator('input[type="file"]')
                        if files.count() == 1:
                            files.set_input_files(str(resume), timeout=2500)
                            print("CV adjuntado en el formulario.")
                        elif files.count() > 1:
                            print("Hay varios campos de archivo; el CV no se adjuntó para evitar elegir uno incorrecto.")
                        else:
                            print("No se encontró campo de archivo; adjunta el CV manualmente si corresponde.")
                    except PlaywrightError as error:
                        print(f"No se pudo adjuntar el CV; hazlo manualmente: {error}")
            except PlaywrightError as error:
                print(f"No se pudo preparar este formulario automáticamente: {error}")
            print("Revisa los campos, destinatario y términos. El programa no pulsa Enviar.")
            input("Envía manualmente si decides postular; luego presiona Enter para continuar… ")
            page.close()
        context.close()
        browser.close()


if __name__ == "__main__":
    main()
