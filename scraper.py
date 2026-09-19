# -*- coding: utf-8 -*-
"""
Modulo de Web Scraping - RESULTADOS DEL DIA (API oficial de la Caja Popular).

ARQUITECTURA (verificada 19/09/2026 con Playwright headless contra la SPA real):
  La Caja Popular expone una API JSON publica detras de su SPA React:
      https://resultadosquiniela.cajapopular.gov.ar/api/extracto/?fecha_sorteo=YYYY-MM-DD
      -> [{id, sorteo, tipo (1-5), tipo_detalle, fecha_sorteo, ...}, ...]
      https://resultadosquiniela.cajapopular.gov.ar/api/extracto-registro/?id=<id>
      -> [{posicion, numero}, ...] (20 premios por sorteo, posicion 0 = "A la cabeza")
      https://resultadosquiniela.cajapopular.gov.ar/api/tipo-sorteo/<1..5>
      -> catalogo de turnos con horarios oficiales.

  Estrategia (en orden):
    1) API JSON directa con requests (rapido, sin browser). ~200ms.
    2) Si la API cambio o se cayo, fallback a CSV local.
    3) Ultimo recurso: mock deterministico por fecha.

  La API NUNCA devuelve 500 al cliente.

  NOTA PLAYWRIGHT: ya no es necesario para el scraping en vivo, pero queda
  instalable para inspeccion (scripts/probe_spa.py lo usa). Si la SPA cambia
  de nuevo y la API se esconde, Playwright permite re-descubrir endpoints.
"""
from __future__ import annotations

import logging
import random
import re
from datetime import date
from typing import Dict, Optional

import requests

from data_loader import HORARIOS_TURNO, TURNOS, cargar_historial, guardar_sorteos_del_dia

LOG = logging.getLogger("quiniela.scraper")

URL_API_BASE = "https://resultadosquiniela.cajapopular.gov.ar/api"
URL_EXTRACTO = f"{URL_API_BASE}/extracto/"           # ?fecha_sorteo=YYYY-MM-DD
URL_REGISTRO = f"{URL_API_BASE}/extracto-registro/"  # ?id=<id>
URL_PRINCIPAL = "https://www.cajapopular.gov.ar/"

# Mapeo del API tipo (1-5) -> nuestro nombre canonico de turno
TIPO_API_A_TURNO = {
    1: "Matutino",
    2: "Vespertino",
    3: "Siesta",      # "DE LA SIESTA"
    4: "Tarde",       # "DE LA TARDE" (19:30 hs)
    5: "Nocturno",
}

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
    "Referer": "https://resultadosquiniela.cajapopular.gov.ar/",
    "Origin": "https://resultadosquiniela.cajapopular.gov.ar",
    "Connection": "keep-alive",
}

TIMEOUT_S = 8


def _get_json(url: str, params: Optional[dict] = None) -> Optional[object]:
    """GET con devolucion JSON. None ante cualquier error."""
    try:
        LOG.info("Scraper: GET %s params=%s", url, params)
        r = requests.get(url, headers=DEFAULT_HEADERS, params=params, timeout=TIMEOUT_S)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        LOG.warning("Scraper: fallo HTTP %s -> %s", url, e.__class__.__name__)
        return None
    except ValueError as e:
        LOG.warning("Scraper: respuesta no-JSON de %s -> %s", url, e)
        return None
    except Exception as e:
        LOG.exception("Scraper: error inesperado en %s: %s", url, e)
        return None


def _extraer_por_api(hoy: date) -> Optional[Dict[str, str]]:
    """Estrategia principal: llama a la API JSON oficial y arma el dict de turnos."""
    data = _get_json(URL_EXTRACTO, params={"fecha_sorteo": hoy.isoformat()})
    if not isinstance(data, list) or not data:
        return None

    resultado: Dict[str, str] = {t: "----" for t in TURNOS}
    sorteos_para_csv: Dict[str, int] = {}

    for entry in data:
        tipo_id = entry.get("tipo")
        turno = TIPO_API_A_TURNO.get(tipo_id)
        if not turno:
            LOG.warning("Scraper: tipo de sorteo desconocido %s en extracto", tipo_id)
            continue
        extracto_id = entry.get("id")
        if not extracto_id:
            continue
        registros = _get_json(URL_REGISTRO, params={"id": extracto_id})
        if not isinstance(registros, list) or not registros:
            continue
        # posicion 0 = "A la cabeza" (primer premio)
        cabeza = next((r for r in registros if r.get("posicion") == 0), None)
        if cabeza is None:
            cabeza = min(registros, key=lambda r: r.get("posicion", 999))
        numero = cabeza.get("numero")
        if numero is None:
            continue
        resultado[turno] = f"{int(numero):04d}"
        sorteos_para_csv[turno] = int(numero)

    if sorteos_para_csv:
        try:
            guardar_sorteos_del_dia(hoy, sorteos_para_csv)
        except Exception as e:
            LOG.exception("Scraper: no pude persistir al CSV: %s", e)

    if all(v == "----" for v in resultado.values()):
        return None
    return resultado


def _fallback_csv(hoy: date) -> Dict[str, str]:
    """Lee el ultimo registro de cada turno con fecha == hoy desde el CSV."""
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
    """Ultimo recurso: numeros pseudo-aleatorios sembrados con la fecha."""
    LOG.warning("Scraper: usando fallback deterministico (seed=%s).", hoy.isoformat())
    rnd = random.Random(f"CPATUC-{hoy.isoformat()}")
    return {t: f"{rnd.randint(0, 9999):04d}" for t in TURNOS}


def obtener_turnos_del_dia(hoy: Optional[date] = None) -> Dict:
    """Devuelve dict de turnos + metadatos de la fuente. Nunca lanza excepcion."""
    hoy = hoy or date.today()
    LOG.info("Scraper: iniciando extraccion para %s", hoy)

    # 1) API JSON oficial
    via_api = _extraer_por_api(hoy)
    if via_api:
        n = sum(1 for v in via_api.values() if v != "----")
        LOG.info("Scraper: extraccion via API oficial OK (%d turnos con datos).", n)
        return {"turnos": via_api, "fuente": "api_caja_popular", "advertencia": None}

    # 2) CSV local
    LOG.warning("Scraper: API no disponible o sin datos. Probando CSV local.")
    csv_turnos = _fallback_csv(hoy)
    if any(v != "----" for v in csv_turnos.values()):
        LOG.info("Scraper: usando datos del CSV local para %s.", hoy)
        return {
            "turnos": csv_turnos,
            "fuente": "historico_csv",
            "advertencia": (
                "No se pudo leer la API de la Caja Popular; mostrando el ultimo "
                "registro del CSV local para los turnos ya sorteados."
            ),
        }

    # 3) Deterministico
    LOG.error("Scraper: ni API ni CSV devolvieron datos. Generando mocks.")
    return {
        "turnos": _fallback_determinista(hoy),
        "fuente": "mock_determinista",
        "advertencia": (
            "Sitio oficial caido y sin datos en CSV. Se muestran numeros "
            "deterministicos del dia (se repiten al recargar)."
        ),
    }


# ---------- Compat: parseo HTML (por si la API se esconde otra vez) ----------

_RE_NUMERO_4_CIFRAS = re.compile(r"\b(\d{4})\b")

_ALIASES = {
    "Matutino":   ["Matutino", "MATUTINO", "Matutina"],
    "Vespertino": ["Vespertino", "VESPERTINO", "Vespertina"],
    "Siesta":     ["Siesta", "SIESTA", "De la Siesta", "de la siesta", "Electrica"],
    "Tarde":      ["Tarde", "TARDE", "De la Tarde", "de la tarde", "Preliminar", "Plus", "Extra"],
    "Nocturno":   ["Nocturno", "NOCTURNO", "Nocturna"],
}


def _parsear_html(html: str) -> Dict[str, str]:
    """Heuristica de parseo HTML (ya no es la via principal)."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    texto = soup.get_text(" ", strip=True)
    resultado: Dict[str, str] = {t: "----" for t in TURNOS}
    for canon in TURNOS:
        for alias in _ALIASES.get(canon, [canon]):
            pat = re.compile(rf"{re.escape(alias)}[^0-9]{{0,40}}(\d{{4}})", re.IGNORECASE)
            m = pat.search(texto)
            if m:
                resultado[canon] = m.group(1)
                break
    return resultado
