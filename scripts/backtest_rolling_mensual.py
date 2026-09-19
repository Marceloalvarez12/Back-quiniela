# -*- coding: utf-8 -*-
"""
Backtest rolling de 30 dias: simula que el modelo se entrena con todo lo
anterior al dia objetivo y predice para ESE dia, sumatoria 1..N.

Para tener muestra decente rapido, este script:
  1) Carga el CSV completo (sintetico + reales del scraper).
  2) Elimina sorteos del mismo (fecha, turno) duplicados (el scraper genera
     algunos duplicados por re-persistencia).
  3) Para cada fecha desde 'dias_atras' hacia atras hasta el inicio del CSV,
     entrena con df[df.fecha < fecha_objetivo] y predice para los 5 turnos
     de esa fecha. Cuenta aciertos top-1/3/5/10.
  4) Resume: precision global, por turno, distribucion de rank.

Muestra minima para conclusion honesta: ~120 sorteos (=24 dias * 5 turnos).
Esta version arranca con lo que haya; corriendolo unos dias con el scraper
activo se acumulan mas.
"""

import sys
from datetime import date, datetime, timedelta
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.insert(0, "D:\\Quiniela\\Back-quiniela")

from data_loader import cargar_historial, TURNOS
from prediccion import (
    _calor_reciente, _calor_historico, _racha_ausencia_actual,
    _afinidad_por_turno, _coocurrencia_con_calientes, _dias_desde_ultima,
    _minmax, DEFAULT_PESOS,
)


def predecir_con_score(df_train: pd.DataFrame, hoy: date) -> dict[str, list[str]]:
    """Devuelve top-10 por cada turno para la fecha `hoy`."""
    s1_raw = _calor_reciente(df_train, ventana=30)
    s2_raw = _calor_historico(df_train)
    s3_raw = _racha_ausencia_actual(df_train)
    s5_raw = _coocurrencia_con_calientes(df_train, ventana=60)
    s6_raw = _dias_desde_ultima(df_train, hoy)
    s1 = _minmax(s1_raw); s2 = _minmax(s2_raw); s3 = 1 - _minmax(s3_raw)
    s5 = _minmax(s5_raw); s6 = 1 - _minmax(s6_raw)

    out: dict[str, list[str]] = {}
    s4_global = {
        t: _minmax(_afinidad_por_turno(df_train, t)) for t in TURNOS
    }

    # Para eficiencia, calculamos s1, s2, s3, s5, s6 una vez (no dependen
    # del turno) y s4 por turno.
    score_base = (
        DEFAULT_PESOS["s1_calor_reciente"]   * s1
        + DEFAULT_PESOS["s2_calor_historico"]  * s2
        + DEFAULT_PESOS["s3_ausencia"]         * s3
        + DEFAULT_PESOS["s5_coocurrencia"]     * s5
        + DEFAULT_PESOS["s6_recencia_inversa"] * s6
    )
    score_0_100_base = _minmax(score_base) * 100.0

    for t in TURNOS:
        score_t = score_base + DEFAULT_PESOS["s4_afinidad_turno"] * s4_global[t]
        s_t = _minmax(score_t) * 100.0
        top_idx = np.argsort(-s_t)[:10]
        out[t] = [f"{int(i):02d}" for i in top_idx]
    return out


def rolling_backtest(dias_atras: int = 30, ventana_minima_train: int = 100,
                    top_k_eval=(1, 3, 5, 10)) -> dict:
    df, fuente = cargar_historial()
    df["fecha_dt"] = pd.to_datetime(df["fecha"], errors="coerce")
    df = df.dropna(subset=["fecha_dt"]).sort_values("fecha_dt").reset_index(drop=True)
    # Dedup por (fecha, turno): si el scraper agrego duplicados, conservamos
    # la ULTIMA (los reales van al final del CSV).
    df = df.drop_duplicates(subset=["fecha", "turno"], keep="last")

    # Conjunto de fechas unicas dentro de los ultimos `dias_atras` dias del CSV
    ultima_fecha = df["fecha_dt"].max().date()
    primera_fecha = df["fecha_dt"].min().date()
    fecha_minima = max(primera_fecha, ultima_fecha - timedelta(days=dias_atras))
    fechas_eval = sorted([
        d.date() for d in df["fecha_dt"].unique()
        if fecha_minima <= d.date() <= ultima_fecha
    ])
    if not fechas_eval:
        return {"error": "no hay fechas para evaluar"}

    print(f"=== BACKTEST ROLLING (ultimos {dias_atras} dias) ===")
    print(f"Fuente: {fuente}")
    print(f"Total CSV: {len(df)} filas | Fechas a evaluar: {len(fechas_eval)} "
          f"({fechas_eval[0]} -> {fechas_eval[-1]})")
    print(f"Turnos por fecha = {len(TURNOS)}\n")

    # Contadores globales
    aciertos = {f"top{k}": 0 for k in top_k_eval}
    por_turno = {t: {f"top{k}": 0 for k in top_k_eval} for t in TURNOS}
    ranks_globales = []
    total_evaluados = 0

    # Por dia para construir tabla
    detalle_por_dia = []

    for fecha in fechas_eval:
        df_antes = df[df["fecha_dt"] < pd.Timestamp(fecha)].copy()
        if len(df_antes) < ventana_minima_train:
            print(f"  {fecha}: train={len(df_antes)} (< {ventana_minima_train}), skip")
            continue

        df_dia = df[df["fecha_dt"] == pd.Timestamp(fecha)].copy()
        df_dia = df_dia[df_dia["turno"].isin(TURNOS)]
        if len(df_dia) == 0:
            continue

        predicciones = predecir_con_score(df_antes, fecha)

        dia_resumen = {"fecha": fecha.isoformat(), "resultados": {}}
        rank_promedio_dia = []

        for _, fila in df_dia.iterrows():
            turno = fila["turno"]
            numero_real = int(fila["numero"])
            term_real_str = f"{numero_real % 100:02d}"
            top10 = predicciones.get(turno, [])
            rank = next((i + 1 for i, n in enumerate(top10) if n == term_real_str), None)
            if rank is None:
                rank = 11  # fuera del top-10
            rank_promedio_dia.append(rank)
            for k in top_k_eval:
                if term_real_str in top10[:k]:
                    aciertos[f"top{k}"] += 1
                    por_turno[turno][f"top{k}"] += 1
            total_evaluados += 1
            ranks_globales.append(rank)
            dia_resumen["resultados"][turno] = {
                "real": term_real_str,
                "rank": rank,
                "top10_predicho": top10,
            }
        if rank_promedio_dia:
            dia_resumen["rank_promedio"] = round(float(np.mean(rank_promedio_dia)), 2)
        detalle_por_dia.append(dia_resumen)

    # Reporte
    print(f"\n=== RESUMEN ({total_evaluados} sorteos en {len(detalle_por_dia)} dias) ===\n")
    print(f"GLOBAL (todos los turnos y dias):")
    for k in top_k_eval:
        pct = 100 * aciertos[f"top{k}"] / max(1, total_evaluados)
        azar = k  # p_azar = k/100
        diff = pct - azar
        flag = " <-- mejor que azar" if diff > 5 else (" <-- peor que azar" if diff < -5 else " (dentro del azar)")
        print(f"  top{k:>2}: {aciertos[f'top{k}']:>3}/{total_evaluados} = {pct:>5.1f}% "
              f"(azar={azar}%, diff={diff:+.1f}%){flag}")

    print(f"\nPOR TURNO:")
    print(f"  {'turno':<12}{'total':>7}{'top1':>7}{'top3':>7}{'top5':>7}{'top10':>8}  rank_promedio")
    for t in TURNOS:
        sub_total = sum(1 for r in ranks_globales
                       if True)  # placeholder, recalculamos abajo
        sub = [{f"top{k}": 0 for k in top_k_eval} for _ in range(0)]
        # Mejor recalcular directo:
        cnt = {f"top{k}": 0 for k in top_k_eval}
        ranks_t = []
        for d in detalle_por_dia:
            res = d["resultados"].get(t, {})
            if "rank" in res:
                ranks_t.append(res["rank"])
                for k in top_k_eval:
                    if res["real"] in res["top10_predicho"][:k]:
                        cnt[f"top{k}"] += 1
        n_t = len(ranks_t)
        if n_t == 0:
            continue
        rank_avg = np.mean(ranks_t) if ranks_t else 0
        print(f"  {t:<12}{n_t:>7}{cnt['top1']:>7}{cnt['top3']:>7}{cnt['top5']:>7}{cnt['top10']:>8}  {rank_avg:>5.2f}")

    print(f"\nDISTRIBUCION DE RANK (promedio, donde mas cae el acierto):")
    if ranks_globales:
        median = float(np.median(ranks_globales))
        mean = float(np.mean(ranks_globales))
        p25 = float(np.percentile(ranks_globales, 25))
        p75 = float(np.percentile(ranks_globales, 75))
        print(f"  rank promedio: {mean:.2f}  mediana: {median:.1f}")
        print(f"  percentil 25%: {p25:.1f}, percentil 75%: {p75:.1f}")
        # Cuantos quedaron fuera del top-10
        fuera = sum(1 for r in ranks_globales if r > 10)
        print(f"  fuera del top-10: {fuera}/{len(ranks_globales)} = {100*fuera/len(ranks_globales):.1f}%")

    return {
        "fuente": fuente,
        "total_evaluados": total_evaluados,
        "dias_evaluados": len(detalle_por_dia),
        "aciertos_global": aciertos,
        "por_turno": por_turno,
        "ranks_globales": ranks_globales,
        "detalle_por_dia": detalle_por_dia,
    }


if __name__ == "__main__":
    # El CSV arranca el 2026-04-23 (~150 dias hasta hoy sep 19).
    # Vamos a evaluar los ultimos 30 dias del CSV que SI tenga.
    res = rolling_backtest(dias_atras=30, ventana_minima_train=100)
