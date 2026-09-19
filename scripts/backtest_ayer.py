"""
Backtest honesto del algoritmo de prediccion.
Corre: 'ayer la prediccion habria dicho esto, y el resultado fue este'.
Calcula precision por turno y overall.

Como el CSV solo guarda los 750 sorteos sinteticos, el 'ayer' REAL seria
2026-09-18 (ultimo dia completo en el CSV). Eso se usa para el backtest
y el dataset se filtra para NO usar el dia en cuestion durante el calculo.
"""

import json
import sys
from datetime import date, timedelta

import numpy as np
import pandas as pd

sys.path.insert(0, "D:\\Quiniela\\Back-quiniela")

from data_loader import cargar_historial, CSV_PATH, TURNOS
from prediccion import construir_prediccion


def backtest(dia_objetivo_iso: str, top_k_eval: tuple = (1, 3, 5, 10)) -> dict:
    df, fuente = cargar_historial()
    if "fecha" not in df.columns:
        return {"error": "sin columna fecha"}

    hoy = pd.Timestamp(dia_objetivo_iso)
    df_ts = df.copy()
    df_ts["fecha_dt"] = pd.to_datetime(df_ts["fecha"], errors="coerce")
    df_ts = df_ts.dropna(subset=["fecha_dt"])

    # Datos REALES del dia objetivo
    reales = df_ts[df_ts["fecha_dt"] == hoy]
    if len(reales) == 0:
        return {"error": f"no hay datos en CSV para {dia_objetivo_iso}"}

    # Hidratamos el CSV entero para usar hasta DIAS ANTERIORES como entrenamiento.
    # Simulamos 'ayer': el predictor calcula con todos los sorteos <= DIAS_ANTERIORES.
    # Para cada turno del dia objetivo, miramos: 'el predictor dijo estos top-k,
    # la terminacion real estuvo en ese top-k?'
    # Y eso lo hacemos por cada turno por separado, y luego lo agregamos.

    detalles = []
    aciertos = {f"top{k}": 0 for k in top_k_eval}
    total = 0

    print(f"=== BACKTEST PARA {dia_objetivo_iso} ===")
    print(f"Fuente: {fuente} | {len(df_ts)} sorteos cargados | {len(reales)} turnos reales ese dia\n")

    for _, fila_real in reales.iterrows():
        turno = fila_real["turno"]
        numero_real_full = int(fila_real["numero"])
        terminacion_real = numero_real_full % 100
        total += 1

        # Construimos un DF con todos los sorteos ESTRICTAMENTE ANTERIORES al dia objetivo.
        df_train = df_ts[df_ts["fecha_dt"] < hoy].copy()
        if len(df_train) < 50:
            print(f"  ! {turno}: solo {len(df_train)} sorteos en el train set, requiere >=50")
            continue

        # Reutilizo la logica de prediccion pero con df recortado y sin mostrar el disclaimer.
        r_pred = construir_prediccion(
            turno=turno,
            pesos=None,
            top_k=max(top_k_eval),
            ventana_reciente=30,
        )
        # pero tenemos que asegurarnos que el calculo uso solo df_train, no el del modulo:
        # -> invocamos las funciones internas en lugar del wrapper global
        from prediccion import (
            _calor_reciente, _calor_historico, _racha_ausencia_actual,
            _coocurrencia_con_calientes, _dias_desde_ultima, _minmax,
            _afinidad_por_turno, DEFAULT_PESOS,
        )
        s1_raw = _calor_reciente(df_train, ventana=30)
        s2_raw = _calor_historico(df_train)
        s3_raw = _racha_ausencia_actual(df_train)
        s4_raw = _afinidad_por_turno(df_train, turno)
        s5_raw = _coocurrencia_con_calientes(df_train, ventana=60)
        s6_raw = _dias_desde_ultima(df_train, hoy.date())
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
        orden = np.argsort(-score_0_100)
        top_idx = orden[:max(top_k_eval)]
        top_numeros = [f"{int(i):02d}" for i in top_idx]
        terminacion_real_str = f"{terminacion_real:02d}"

        rank = next((i + 1 for i, idx in enumerate(top_idx) if int(idx) == terminacion_real), None)
        acerto = {}
        for k in top_k_eval:
            acerto[f"top{k}"] = terminacion_real_str in top_numeros[:k]
            if acerto[f"top{k}"]:
                aciertos[f"top{k}"] += 1

        detalles.append({
            "turno": turno,
            "numero_real": f"{numero_real_full:04d}",
            "terminacion_real": terminacion_real_str,
            "rank": rank,
            "top10_predicho": top_numeros[:10],
            "score_top1": round(float(score_0_100[top_idx[0]]), 2),
            "score_real": round(float(score_0_100[terminacion_real]), 2) if rank else None,
            "acierto": acerto,
        })

        flag = "".join("X" if acerto[f"top{k}"] else "." for k in top_k_eval)
        print(f"  {turno:11s} => real {terminacion_real_str} (full {numero_real_full:04d}) "
              f"rank={rank or 'fuera'} | top{top_k_eval} = {flag}")

    print()
    res = {
        "fecha": dia_objetivo_iso,
        "fuente_datos": fuente,
        "total_turnos_evaluados": total,
        "precision": {
            f"top{k}": {
                "aciertos": aciertos[f"top{k}"],
                "total": total,
                "ratio": round(aciertos[f"top{k}"] / total, 4) if total else 0,
            }
            for k in top_k_eval
        },
        "detalles": detalles,
    }
    print(f"RESUMEN: {aciertos} / {total} turnos")
    print(f"  top1 : {100*aciertos['top1']/max(1,total):.1f}%")
    print(f"  top3 : {100*aciertos['top3']/max(1,total):.1f}%")
    print(f"  top5 : {100*aciertos['top5']/max(1,total):.1f}%")
    print(f"  top10: {100*aciertos['top10']/max(1,total):.1f}%")
    print(f"Para comparar:azar puro al top5=5%, top10=10%")
    return res


if __name__ == "__main__":
    ayer_iso = "2026-09-18"  # ultimo dia completo en el CSV sintetico
    r = backtest(ayer_iso)
    with open("backtest_ayer.json", "w", encoding="utf-8") as f:
        # pandas Timestamp -> iso
        def _normalize(o):
            if isinstance(o, (pd.Timestamp, date)): return o.isoformat()
            if isinstance(o, np.integer): return int(o)
            if isinstance(o, (np.integer, np.int64)): return int(o)
            return o
        json.dump(r, f, ensure_ascii=False, indent=2, default=_normalize)
    print("\nResultado guardado en backtest_ayer.json")
