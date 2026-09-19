"""
Análisis estadístico con Pandas/NumPy sobre el historial de sorteos.
- "calientes": 5 terminaciones (00-99) más frecuentes como "A la cabeza".
- "demorados": 5 terminaciones que más sorteos consecutivos llevan sin salir
  como "A la cabeza" (racha actual de ausencia).
"""
from __future__ import annotations

import logging
from typing import Dict, List

import numpy as np
import pandas as pd

from data_loader import cargar_historial

LOG = logging.getLogger("quiniela.stats")


def _top_calientes(df: pd.DataFrame, k: int = 5) -> List[Dict[str, int]]:
    """Top K terminaciones de 2 cifras con mayor frecuencia absoluta."""
    conteo = (
        df["terminacion"]
        .value_counts()          # incluye NaN si los hubiera
        .head(100)               # todas las posibles terminaciones
    )
    # Aseguramos que aparezcan las 100 (aunque con freq=0) para que el top
    # no esté sesgado si faltan registros históricos.
    todos = pd.Series(0, index=range(100), dtype="int64")
    todos.update(conteo.astype("int64"))
    top = todos.sort_values(ascending=False).head(k)
    return [{"numero": f"{int(n):02d}", "frecuencia": int(f)} for n, f in top.items()]


def _top_demorados(df: pd.DataFrame, k: int = 5) -> List[Dict[str, int]]:
    """Top K terminaciones con la racha actual de ausencia más larga.

    Recorremos el DF en orden cronológico ascendente y, para cada
    terminación 0..99, llevamos un contador 'sorteos_sin_salir' que se
    reinicia cuando esa terminación aparece como 'A la cabeza'.
    """
    df = df.sort_values("fecha").reset_index(drop=True)
    rachas = np.zeros(100, dtype="int64")
    for term in df["terminacion"].astype("Int64").to_numpy():
        if pd.isna(term):
            continue
        # Todos los números que NO salieron en este sorteo suman +1 a su racha;
        # el que salió vuelve a 0.
        salir = np.ones(100, dtype=bool)
        salir[int(term)] = False
        rachas[salir] += 1
        rachas[int(term)] = 0
    # Top K con mayor racha; empates → terminación más baja primero.
    orden = np.lexsort((np.arange(100), -rachas))  # -rachas: descendente
    top = orden[:k]
    return [
        {"numero": f"{int(n):02d}", "sorteos_sin_salir": int(rachas[n])}
        for n in top
    ]


def construir_estadisticas(turnos_del_dia: Dict[str, str]) -> Dict:
    df, fuente = cargar_historial()
    LOG.info("Estadísticas calculadas sobre %d sorteos (fuente=%s).", len(df), fuente)

    calientes = _top_calientes(df, k=5)
    demorados = _top_demorados(df, k=5)

    return {
        "calientes": calientes,
        "demorados": demorados,
        "turnos_del_dia": turnos_del_dia,
        "fuente_datos": fuente,
        "total_sorteos_analizados": int(len(df)),
    }
