"""
Carga y mantenimiento del historial de sorteos.

Prioridad de carga:
  1) data/historico_base.csv (si existe) — registros reales o curados.
  2) Generación determinística in-memory — 600 sorteos pseudo-aleatorios
     sembrados con la fecha de build, repetibles hasta que cambies la semilla.

Formato CSV (cabecera fija):
  fecha,turno,numero
  2025-01-01,Matutina,4523
  2025-01-01,Electrica,0987
  ...

'numero' es el premio "A la cabeza" completo (hasta 4 cifras).
Para estadísticas se usa la terminación de 2 cifras (numero % 100).
"""
from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

LOG = logging.getLogger("quiniela.data")

DATA_DIR = Path(__file__).parent / "data"
CSV_PATH = DATA_DIR / "historico_base.csv"

TURNOS = ("Matutina", "Electrica", "Vespertina", "Nocturna")


def _generar_sorteos_simulados(n_dias: int = 150, semilla: int = 20250919) -> pd.DataFrame:
    """Genera un historial sintético pero coherente: 4 turnos por día × n_dias."""
    rng = np.random.default_rng(semilla)
    hoy = date.today()
    filas: List[dict] = []
    for i in range(n_dias):
        d = hoy - timedelta(days=n_dias - 1 - i)
        for turno in TURNOS:
            # Pesos suaves: terminaciones 00..99 con una distribución levemente
            # sesgada para que "calientes" y "demorados" tengan sentido al graficar.
            pesos = rng.dirichlet(np.ones(100) * 0.5)
            terminacion = int(rng.choice(np.arange(100), p=pesos))
            # Generamos un número de 4 cifras respetando la terminación.
            prefijo = int(rng.integers(0, 100))
            numero = prefijo * 100 + terminacion
            filas.append({"fecha": d.isoformat(), "turno": turno, "numero": numero})
    return pd.DataFrame(filas, columns=["fecha", "turno", "numero"])


def cargar_historial() -> tuple[pd.DataFrame, str]:
    """Devuelve (df, fuente). df tiene columnas: fecha, turno, numero, terminacion."""
    if CSV_PATH.exists():
        try:
            df = pd.read_csv(CSV_PATH, dtype={"fecha": str, "turno": str, "numero": "Int64"})
            if {"fecha", "turno", "numero"}.issubset(df.columns) and len(df) >= 50:
                df["terminacion"] = df["numero"].astype("Int64") % 100
                LOG.info("Historial cargado desde %s (%d filas)", CSV_PATH, len(df))
                return df, "historico_csv"
            LOG.warning("CSV presente pero con formato/cantidad insuficiente (%d filas).", len(df))
        except Exception as e:
            LOG.exception("No se pudo leer %s: %s. Genero simulados.", CSV_PATH, e)

    # Fallback: simulado in-memory. Semilla fija → números repetibles.
    LOG.info("Generando historial simulado (fallback determinístico).")
    sim = _generar_sorteos_simulados()
    sim["terminacion"] = sim["numero"].astype("int64") % 100
    return sim, "simulado_inicial"


def guardar_sorteos_del_dia(fecha: date, sorteos: dict[str, str]) -> None:
    """Si el scraper consigue datos reales, los persiste al CSV para no perderlos."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    existe = CSV_PATH.exists()
    with open(CSV_PATH, "a", encoding="utf-8", newline="") as f:
        if not existe:
            f.write("fecha,turno,numero\n")
        for turno, num in sorteos.items():
            if num and num != "----":
                f.write(f"{fecha.isoformat()},{turno},{int(num)}\n")
    LOG.info("Sorteos del día %s persistidos en %s", fecha, CSV_PATH)


def write_initial_csv_if_missing() -> None:
    """Crea un historico_base.csv inicial con 600 registros simulados la primera vez.
    Después podés reemplazarlo por datos reales verificados a mano."""
    if CSV_PATH.exists() and os.path.getsize(CSV_PATH) > 1000:
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    sim = _generar_sorteos_simulados(n_dias=150, semilla=20250919)
    sim.to_csv(CSV_PATH, index=False)
    LOG.info("historico_base.csv inicial escrito en %s (%d filas)", CSV_PATH, len(sim))
