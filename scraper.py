"""
Módulo de Web Scraping — RESULTADOS DEL DÍA.

URL oficial: https://cajapopular.gov.ar
La página principal NO contiene los resultados del día (es un sitio WordPress/Divi
con entradas de blog). Los resultados viven en una SPA React separada en
https://resultadosquiniela.cajapopular.gov.ar/, que carga datos vía una API
interna no documentada (/api/...) que solo se ve dentro del bundle JS minificado.

Estrategia (en orden, todas con timeout corto para no colgar la API):
  1) Intento HTTP a cajapopular.gov.ar por si algún día exponen resultados
     en HTML estático (no es el caso hoy, pero el código queda preparado).
  2) Si falla, intento HTTP a resultadosquiniela.cajapopular.gov.ar por la
     misma razón.
  3) Si todo falla → fallback determinístico desde data/historico_base.csv
     (último registro de cada turno que sea del día de hoy) o, en el peor
     de los casos, un set generado con seed = fecha + "CPATUC".
  4) La API NUNCA devuelve 500: esto se traduce a un dict {"fuente": "..."}.

NOTA SOBRE JAVASCRIPT / PLAYWRIGHT:
  La web oficial carga los números con React. Si en el futuro querés
  renderizado JS real, instalá playwright y reemplazá `_fetch_html` por:
      from playwright.sync_api import sync_playwright
      with sync_playwright() as p:
          browser = p.chromium.launch()
          page = browser.new_page()
          page.goto(URL_RESULTADOS, wait_until="networkidle")
          html = page.content()
          browser.close()
  Y luego parseá con BeautifulSoup.  El resto del módulo no requiere cambios.
"""
from __future__ import annotations

import logging
import random
import re
from datetime import date
from typing import Dict

import requests
from bs4 import BeautifulSoup

from data_loader import CSV_PATH, TURNOS, cargar_historial

LOG = logging.getLogger("quiniela.scraper")

# URLs reales verificadas hoy (sep 2026). El sitio principal redirige 301 a www.
URL_PRINCIPAL = "https://www.cajapopular.gov.ar/index.php/1249-2/"      # sección "Juegos"
URL_RESULTADOS = "https://resultadosquiniela.cajapopular.gov.ar/"       # SPA React

# Mapa de turno → hora aproximada de sorteo en Tucumán. Sirve para decidir
# qué turnos mostrar reales y cuáles dejar como "----" según la hora.
HORARIOS_TURNO = {  # hora local AR
    "Matutina":   (10, 30),
    "Electrica":  (15, 0),
    "Vespertina": (18, 0),
    "Nocturna":   (21, 0),
}

# Headers que simulan un Chrome real en Windows. Sin esto, muchos sitios
# devuelven 403/503 o un HTML ofuscado.
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

TIMEOUT_S = 6  # corto, no podemos colgarnos


def _fetch_html(url: str) -> str | None:
    """Intenta descargar HTML estático. Devuelve None ante cualquier error."""
    try:
        LOG.info("Scraper: GET %s", url)
        r = requests.get(url, headers=DEFAULT_HEADERS, timeout=TIMEOUT_S, allow_redirects=True)
        r.raise_for_status()
        # Algunos servers WP devuelven 200 con body vacío si detectan bot
        if len(r.text) < 500:
            LOG.warning("Scraper: respuesta demasiado corta (%d bytes) de %s", len(r.text), url)
            return None
        return r.text
    except requests.RequestException as e:
        LOG.warning("Scraper: fallo HTTP en %s → %s", url, e.__class__.__name__)
        return None
    except Exception as e:
        LOG.exception("Scraper: error inesperado en %s: %s", url, e)
        return None


# ---------- Parseo heurístico del HTML ----------
# Estas regex buscan cualquier bloque que contenga los 4 turnos oficiales.
# La web oficial puede cambiar el markup mañana; las regex son lo bastante
# laxas como para sobrevivir un rediseño menor.

_RE_NUMERO_4_CIFRAS = re.compile(r"\b(\d{4})\b")
_RE_TURNO_HORARIO = re.compile(
    r"(Matutina|El[eé]ctrica|El[eé]ctrica\s*/\s*Siesta|Siesta|Vespertina|Nocturna)",
    re.IGNORECASE,
)


def _parsear_html(html: str) -> Dict[str, str]:
    """Heurística: busca etiquetas de turno y el número de 4 cifras más cercano.
    Si la SPA expone números visibles en el DOM, los captura; si no, devuelve
    un dict con '----' en todo."""
    soup = BeautifulSoup(html, "html.parser")
    texto = soup.get_text(" ", strip=True)

    # Caso típico: el sitio tiene una grilla o tabla <table> con los premios.
    # Recorremos todas las filas: si el texto de la fila contiene un nombre
    # de turno, capturamos el primer número de 4 cifras que le siga.
    resultado: Dict[str, str] = {t: "----" for t in TURNOS}

    # 1) Tablas
    for fila in soup.find_all(["tr", "div", "section", "article"]):
        t = fila.get_text(" ", strip=True)
        if not t or len(t) > 800:
            continue
        m_turno = _RE_TURNO_HORARIO.search(t)
        if not m_turno:
            continue
        turno_txt = m_turno.group(1)
        # Normalizamos el alias al nombre canónico.
        canon = _canonizar_turno(turno_txt)
        if not canon or resultado[canon] != "----":
            continue
        m_num = _RE_NUMERO_4_CIFRAS.search(t, m_turno.end())
        if m_num:
            resultado[canon] = m_num.group(1)

    if all(v == "----" for v in resultado.values()):
        # 2) Plan B: parseo lineal del texto plano.
        for canon in TURNOS:
            aliases = _ALIASES.get(canon, [canon])
            for alias in aliases:
                pat = re.compile(
                    rf"{re.escape(alias)}[^0-9]{{0,40}}(\d{{4}})",
                    re.IGNORECASE,
                )
                m = pat.search(texto)
                if m:
                    resultado[canon] = m.group(1)
                    break

    return resultado


_ALIASES = {
    "Matutina": ["Matutina", "MATUTINA"],
    "Electrica": ["Electrica", "Eléctrica", "Siesta", "ELÉCTRICA", "ELECTRICA"],
    "Vespertina": ["Vespertina", "VESPERTINA"],
    "Nocturna": ["Nocturna", "NOCTURNA"],
}


def _canonizar_turno(s: str) -> str | None:
    s_norm = s.lower().replace("é", "e").strip()
    if "matutin" in s_norm:
        return "Matutina"
    if "electr" in s_norm or "siesta" in s_norm:
        return "Electrica"
    if "vespertin" in s_norm:
        return "Vespertina"
    if "nocturn" in s_norm:
        return "Nocturna"
    return None


def _fallback_csv(hoy: date) -> Dict[str, str]:
    """Lee el último registro de cada turno cuya fecha == hoy desde el CSV."""
    df, _ = cargar_historial()
    df["fecha"] = df["fecha"].astype(str)
    hoy_str = hoy.isoformat()
    out = {t: "----" for t in TURNOS}
    if "fecha" not in df.columns:
        return out
    sub = df[df["fecha"] == hoy_str]
    if sub.empty:
        return out
    for _, row in sub.iterrows():
        turno = row["turno"]
        if turno in out:
            out[turno] = f"{int(row['numero']):04d}"
    return out


def _fallback_determinista(hoy: date) -> Dict[str, str]:
    """Último recurso: números pseudo-aleatorios sembrados con la fecha,
    visibles y reproducibles durante todo el día."""
    LOG.warning("Scraper: usando fallback deterministico (seed=%s).", hoy.isoformat())
    rnd = random.Random(f"CPATUC-{hoy.isoformat()}")
    return {t: f"{rnd.randint(0, 9999):04d}" for t in TURNOS}


def obtener_turnos_del_dia(hoy: date | None = None) -> Dict:
    """Devuelve el dict de turnos más metadatos de la fuente utilizada."""
    hoy = hoy or date.today()
    LOG.info("Scraper: iniciando extracción para %s", hoy)

    # 1) Intento de scraping real (HTML estático).
    html = _fetch_html(URL_RESULTADOS) or _fetch_html(URL_PRINCIPAL)
    if html:
        parsed = _parsear_html(html)
        if any(v != "----" for v in parsed.values()):
            LOG.info("Scraper: extraccion exitosa de HTML estatico.")
            return {"turnos": parsed, "fuente": "scraper", "advertencia": None}

    # 2) Fallback 1: CSV con datos del día.
    LOG.warning("Scraper: HTML no expuso numeros. Probando CSV local.")
    csv_turnos = _fallback_csv(hoy)
    if any(v != "----" for v in csv_turnos.values()):
        LOG.info("Scraper: usando datos del CSV local para %s.", hoy)
        return {
            "turnos": csv_turnos,
            "fuente": "historico_csv",
            "advertencia": (
                "No se pudo leer el sitio oficial; mostrando el último "
                "registro del CSV local para los turnos ya sorteados."
            ),
        }

    # 3) Fallback 2: determinístico (sembrado por fecha).
    LOG.error("Scraper: ni sitio ni CSV devolvieron datos. Generando mocks.")
    return {
        "turnos": _fallback_determinista(hoy),
        "fuente": "mock_determinista",
        "advertencia": (
            "Sitio oficial caído y sin datos en CSV. Se muestran números "
            "determinísticos del día (se repiten al recargar)."
        ),
    }
