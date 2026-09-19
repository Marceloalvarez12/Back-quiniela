# -*- coding: utf-8 -*-
"""
Backtest REAL contra los 3 sorteos de hoy (19/09) que el scraper capturo.
Para cada sorteo, entrena SOLO con sorteos anteriores (sin leak) y evalua
si la terminacion real estuvo en el top-K de la prediccion.
"""
import json
import sys
from datetime import date

import numpy as np
import pandas as pd

sys.path.insert(0, "D:\\Quiniela\\Back-quiniela")

from data_loader import cargar_historial
from prediccion import (
    _calor_reciente, _calor_historico, _racha_ausencia_actual,
    _afinidad_por_turno, _coocurrencia_con_calientes, _dias_desde_ultima,
    _minmax, DEFAULT_PESOS,
)


def backtest_hoy(dia_iso: str = "2026-09-19", top_k_eval=(1, 3, 5, 10)):
    df, fuente = cargar_historial()
    df["fecha_dt"] = pd.to_datetime(df["fecha"], errors="coerce")
    df = df.dropna(subset=["fecha_dt"])

    reales = df[df["fecha"] == dia_iso].copy()
    # Dejar la ULTIMA aparicion de cada turno (los reales del scraper se agregan
    # al final del CSV; los sinteticos iniciales quedan primero).
    reales = reales.drop_duplicates(subset=["turno"], keep="last")
    if len(reales) == 0:
        print(f"No hay sorteos para {dia_iso}")
        return

    print(f"=== BACKTEST {dia_iso} (primeros registros, sin duplicados) ===")
    print(f"Fuente: {fuente} | Total CSV: {len(df)} filas | Sorteos a evaluar: {len(reales)}\n")

    aciertos = {f"top{k}": 0 for k in top_k_eval}
    detalles = []
    total = 0

    for _, fila in reales.iterrows():
        turno = fila["turno"]
        numero_real = int(fila["numero"])
        term_real = numero_real % 100
        term_real_str = f"{term_real:02d}"

        # El turno a evaluar tiene hora; simulo 'antes del sorteo' usando
        # solo registros de fechas ANTERIORES al dia objetivo. Es lo mas
        # conservador: ignora los sorteos anteriores del MISMO dia.
        df_train = df[df["fecha"] < dia_iso].copy()
        if len(df_train) < 50:
            print(f"  ! {turno}: train set muy chico ({len(df_train)})")
            continue

        s1_raw = _calor_reciente(df_train, ventana=30)
        s2_raw = _calor_historico(df_train)
        s3_raw = _racha_ausencia_actual(df_train)
        s4_raw = _afinidad_por_turno(df_train, turno)
        s5_raw = _coocurrencia_con_calientes(df_train, ventana=60)
        s6_raw = _dias_desde_ultima(df_train, date.fromisoformat(dia_iso))

        s1 = _minmax(s1_raw); s2 = _minmax(s2_raw); s3 = 1 - _minmax(s3_raw)
        s4 = _minmax(s4_raw); s5 = _minmax(s5_raw); s6 = 1 - _minmax(s6_raw)
        score = (
            DEFAULT_PESOS["s1_calor_reciente"]   * s1
            + DEFAULT_PESOS["s2_calor_historico"]  * s2
            + DEFAULT_PESOS["s3_ausencia"]         * s3
            + DEFAULT_PESOS["s4_afinidad_turno"]   * s4
            + DEFAULT_PESOS["s5_coocurrencia"]     * s5
            + DEFAULT_PESOS["s6_recencia_inversa"] * s6
        )
        score_0_100 = _minmax(score) * 100.0

        top_k = max(top_k_eval)
        top_idx = np.argsort(-score_0_100)[:top_k]
        top_numeros = [f"{int(i):02d}" for i in top_idx]

        rank = next((i + 1 for i, idx in enumerate(top_idx) if int(idx) == term_real), None)
        acerto = {f"top{k}": term_real_str in top_numeros[:k] for k in top_k_eval}
        for k in top_k_eval:
            if acerto[f"top{k}"]:
                aciertos[f"top{k}"] += 1
        total += 1

        flag = "".join("X" if acerto[f"top{k}"] else "." for k in top_k_eval)
        print(f"  {turno:11s} => real {term_real_str} (full {numero_real:04d}) "
              f"rank={rank or 'fuera'} | top(1,3,5,10) = {flag}")
        print(f"      top10 predicho: {top_numeros}")

        detalles.append({
            "turno": turno,
            "numero_real": f"{numero_real:04d}",
            "terminacion_real": term_real_str,
            "rank": rank,
            "top10_predicho": top_numeros,
            "acierto": acerto,
        })

    print(f"\n=== RESUMEN ({total} sorteos) ===")
    for k in top_k_eval:
        pct = 100 * aciertos[f"top{k}"] / max(1, total)
        azar = 100 * k / 100
        print(f"  {k:>2}: {aciertos[f'top{k}']}/{total} = {pct:.1f}%  (azar={azar:.0f}%)")

    return {
        "fecha": dia_iso,
        "total": total,
        "aciertos": aciertos,
        "detalles": detalles,
    }


if __name__ == "__main__":
    backtest_hoy("2026-09-19")
