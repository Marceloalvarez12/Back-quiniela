"""Captura el HTML renderizado de la SPA de resultados para inspeccionar el DOM real."""
import sys
from playwright.sync_api import sync_playwright

URL = "https://resultadosquiniela.cajapopular.gov.ar/"

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
    reqs = []
    page.on("request", lambda r: reqs.append(r.url))
    page.goto(URL, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(3000)  # dar tiempo a los fetch de la app
    html = page.content()
    with open("dom_renderizado.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"DOM guardado ({len(html)} bytes)")
    print("--- fetches a /api/ ---")
    seen = set()
    for r in reqs:
        if "/api/" in r or "resultad" in r.lower():
            if r not in seen:
                seen.add(r)
                print(" ", r[:150])
    b.close()
