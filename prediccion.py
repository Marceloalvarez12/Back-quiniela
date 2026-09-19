"""
Modulo de prediccion / patrones / combinaciones.

Disclaimer: la quiniela es ALEATORIA. Cada terminacion 0..99 tiene 1/100 de
probabilidad real en el proximo sorteo. Este modulo solo construye una
heuristica RECREATIVA basada en senales historicas. No garantiza nada.

Senales combinadas en un score 0-100:
  1. Calor reciente   - frecuencia en los ultimos N sorteos (30 default)
  2. Calor historico  - frecuencia historica completa
  3. Ausencia         - sorteos consecutivos sin salir (penaliza)
  4. Afinidad turno   - frecuencia condicionada al turno elegido
  5. Co-ocurrencia    - cuantos sorteos de los top-calientes la acompanaron
  6. Recencia inversa - dias desde ultima aparicion (leve penalizacion)

El score NO es una probabilidad real, es un ranking recreativo.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import date
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from data_loader import cargar_historial

LOG = logging.getLogger("quiniela.prediccion")

# Pesos por defecto para las 6 senales. Tunear via query param.
DEFAULT_PESOS: Dict[str, float] = {
    "s1_calor_reciente":   2.0,
    "s2_calor_historico":  1.5,
    "s3_ausencia":         1.0,    # penaliza
    "s4_afinidad_turno":   1.8,
    "s5_coocurrencia":     1.2,
    "s6_recencia_inversa": -0.8,  # negativo: bajó score si salió ayer
}


def _parse_pesos(raw: Optional[str]) -> Dict[str, float]:
    """`?pesos={"s1_calor_reciente":3.0,...}` -> dict mergeado sobre DEFAULT_PESOS."""
    pesos = dict(DEFAULT_PESOS)
    if not raw:
        return pesos
    try:
        override = json.loads(raw)
        if isinstance(override, dict):
            for k, v in override.items():
                if k in pesos and isinstance(v, (int, float)):
                    pesos[k] = float(v)
    except Exception as e:
        LOG.warning("No pude parsear 'pesos=%s': %s. Uso DEFAULT.", raw, e)
    return pesos


def _calor_reciente(df: pd.DataFrame, ventana: int = 30) -> np.ndarray:
    """Cuenta la frecuencia de cada terminacion en los ultimos `ventana` sorteos."""
    ult = df.tail(ventana)
    conteo = np.zeros(100, dtype=np.float64)
    if len(ult) > 0:
        terminaciones = ult["terminacion"].astype(int).to_numpy()
        for t in terminaciones:
            conteo[t] += 1.0
    return conteo


def _calor_historico(df: pd.DataFrame) -> np.ndarray:
    """Frecuencia total historica."""
    conteo = np.zeros(100, dtype=np.float64)
    terminaciones = df["terminacion"].astype(int).to_numpy()
    for t in terminaciones:
        conteo[t] += 1.0
    return conteo


def _racha_ausencia_actual(df: pd.DataFrame) -> np.ndarray:
    """Cantidad de sorteos consecutivos que cada terminacion NO salio (ultimo estado)."""
    df = df.sort_values("fecha").reset_index(drop=True)
    rachas = np.zeros(100, dtype=np.float64)
    for term in df["terminacion"].astype(int).to_numpy():
        salir = np.ones(100, dtype=bool)
        salir[int(term)] = False
        rachas[salir] += 1
        rachas[int(term)] = 0
    return rachas


def _afinidad_por_turno(df: pd.DataFrame, turno: str) -> np.ndarray:
    """Frecuencia de cada terminacion restringida al turno elegido."""
    sub = df[df["turno"].astype(str) == turno]
    conteo = np.zeros(100, dtype=np.float64)
    if len(sub) > 0:
        terminaciones = sub["terminacion"].astype(int).to_numpy()
        for t in terminaciones:
            conteo[t] += 1.0
    return conteo


def _coocurrencia_con_calientes(
    df: pd.DataFrame, top_k: int = 5, ventana: int = 60
) -> np.ndarray:
    """Cuenta cuantas veces una terminacion salio en el MISMO sorteo que
    alguno de los `top_k` calientes recientes. Esto captura "vienen juntos"."""
    ult = df.tail(ventana).reset_index(drop=True)
    if len(ult) == 0:
        return np.zeros(100, dtype=np.float64)
    # Frecuencia global reciente
    full = np.zeros(100, dtype=np.int64)
    for t in ult["terminacion"].astype(int).to_numpy():
        full[t] += 1
    calientes_idx = np.argsort(-full)[:top_k]
    # Por cada terminacion, contar cuantos sorteos recientes la incluyen
    # simultaneamente con al menos uno de los calientes_idx
    co = np.zeros(100, dtype=np.float64)
    for _, fila in ult.iterrows():
        term = int(fila["terminacion"])
        presentes = {term}
        # En un sorteo real hay muchos premios; como solo guardamos "A la cabeza"
        # la co-ocurrencia se evalua contra OTROS sorteos donde el term aparece
        # junto con algun caliente. Simplificacion: cercanas en el tiempo.
        pass
    # Version simplificada y honesta:
    # score alto si la terminacion suele aparecer en una ventana de 7 dias
    # alrededor de un sorteo donde salio un top-caliente.
    co_ocurrencias = np.zeros(100, dtype=np.float64)
    if len(ult) < 2:
        return co_ocurrencias
    ult_sorted = ult.sort_values("fecha").reset_index(drop=True)
    fechas_calientes = (
        ult_sorted[ult_sorted["terminacion"].astype(int).isin(calientes_idx)]
        ["fecha"].astype(str).tolist()
    )
    for _, fila in ult_sorted.iterrows():
        term = int(fila["terminacion"])
        if term in calientes_idx:
            continue
        fecha = str(fila["fecha"])
        # Vecindad: +/- 7 dias de algun caliente
        hit = False
        for fc in fechas_calientes:
            try:
                a, b = date.fromisoformat(fecha), date.fromisoformat(fc)
                if abs((a - b).days) <= 7:
                    hit = True
                    break
            except Exception:
                pass
        if hit:
            co_ocurrencias[term] += 1.0
    return co_ocurrencias


def _dias_desde_ultima(df: pd.DataFrame, hoy: date) -> np.ndarray:
    """Cantidad de dias desde la ultima aparicion de cada terminacion."""
    hoy_str = hoy.isoformat()
    ult = np.full(100, 9999, dtype=np.float64)
    if len(df) == 0:
        return ult
    df_sorted = df.sort_values("fecha").reset_index(drop=True)
    df_sorted["fecha_dt"] = pd.to_datetime(df_sorted["fecha"], errors="coerce")
    valid = df_sorted.dropna(subset=["fecha_dt"])
    if len(valid) == 0:
        return ult
    valid["dias"] = (pd.Timestamp(hoy) - valid["fecha_dt"]).dt.days
    for _, fila in valid.iterrows():
        term = int(fila["terminacion"])
        dias = float(fila["dias"])
        if dias >= 0 and dias < ult[term]:
            ult[term] = dias
    return ult


def _minmax(arr: np.ndarray) -> np.ndarray:
    """Normaliza un array a [0, 1] min-max. Devuelve 0 si el array es plano."""
    a_min, a_max = float(arr.min()), float(arr.max())
    if a_max == a_min:
        return np.zeros_like(arr)
    return (arr - a_min) / (a_max - a_min)


def construir_prediccion(
    turno: Optional[str] = None,
    pesos: Optional[Dict[str, float]] = None,
    top_k: int = 10,
    ventana_reciente: int = 30,
) -> Dict:
    """Devuelve la prediccion: top_k terminaciones con score y desglose."""
    pesos = pesos or DEFAULT_PESOS
    df, fuente = cargar_historial()
    LOG.info(
        "Prediccion sobre %d sorteos (fuente=%s, turno=%s, top=%d)",
        len(df), fuente, turno or "*", top_k,
    )

    if len(df) < 20:
        return {
            "disclaimer": "Datos insuficientes para una prediccion estable.",
            "top": [],
            "fuente_datos": fuente,
            "turno": turno,
            "total_sorteos_analizados": int(len(df)),
        }

    hoy = date.today()

    # Senales crudas
    s1_raw = _calor_reciente(df, ventana=ventana_reciente)        # +score si alto
    s2_raw = _calor_historico(df)                                  # +score si alto
    s3_raw = _racha_ausencia_actual(df)                            # -score si alto
    s4_raw = _afinidad_por_turno(df, turno) if turno else None     # +score si alto
    s5_raw = _coocurrencia_con_calientes(df, ventana=60)           # +score si alto
    s6_raw = _dias_desde_ultima(df, hoy)                           # -score si bajo (salió ayer)

    # Normalizacion
    s1 = _minmax(s1_raw); s2 = _minmax(s2_raw); s3 = 1 - _minmax(s3_raw)
    s5 = _minmax(s5_raw); s6 = 1 - _minmax(s6_raw)
    s4 = _minmax(s4_raw) if s4_raw is not None else np.zeros(100, dtype=np.float64)

    # Score total
    score = (
        pesos["s1_calor_reciente"]   * s1
        + pesos["s2_calor_historico"]  * s2
        + pesos["s3_ausencia"]         * s3
        + pesos["s4_afinidad_turno"]   * s4
        + pesos["s5_coocurrencia"]     * s5
        + pesos["s6_recencia_inversa"] * s6
    )
    score_0_100 = _minmax(score) * 100.0

    # Top
    orden = np.argsort(-score_0_100)
    top_idx = orden[:top_k]
    top: List[Dict] = []
    for rank, idx in enumerate(top_idx, 1):
        i = int(idx)
        top.append({
            "rank":                 rank,
            "numero":               f"{i:02d}",
            "score":                round(float(score_0_100[i]), 2),
            "calor_reciente":       int(s1_raw[i]),
            "calor_historico":      int(s2_raw[i]),
            "racha_ausencia":       int(s3_raw[i]),  # sorteos sin salir hasta hoy (0 si salio hoy)
            "afinidad_turno":       int(s4_raw[i]) if s4_raw is not None else None,
            "coocurrencias":        int(s5_raw[i]),
            "dias_desde_ultima":    int(min(s6_raw[i], 9999)),
            "componentes_normalizados": {
                "s1_calor_reciente":   round(float(s1[i]), 3),
                "s2_calor_historico":  round(float(s2[i]), 3),
                "s3_ausencia":         round(float(s3[i]), 3),
                "s4_afinidad_turno":   round(float(s4[i]), 3),
                "s5_coocurrencia":     round(float(s5[i]), 3),
                "s6_recencia_inversa": round(float(s6[i]), 3),
            },
        })

    return {
        "disclaimer": (
            "Recreacional. La quiniela es aleatoria; el score ranking es una "
            "heuristica basada en patrones historicos, NO es probabilidad real."
        ),
        "turno":           turno,
        "top":             top,
        "pesos_usados":    pesos,
        "fuente_datos":    fuente,
        "total_sorteos_analizados": int(len(df)),
        "ventana_reciente": ventana_reciente,
    }


# -------- Combinaciones (pares / trios) frecuentes --------

def construir_combinaciones(tipo: str = "pares", top_k: int = 10) -> Dict:
    """Busca combinaciones de numeros que suelen aparecer juntos."""
    if tipo not in ("pares", "trios", "secuencias_dia"):
        tipo = "pares"
    df, fuente = cargar_historial()
    LOG.info("Combinaciones tipo=%s sobre %d sorteos.", tipo, len(df))

    if len(df) < 20:
        return {"tipo": tipo, "combinaciones": [],
                "fuente_datos": fuente, "total_sorteos_analizados": int(len(df))}

    combinaciones: List[Dict] = []
    if tipo in ("pares", "trios"):
        # Para cada fecha, juntamos los 5 premios del dia y medimos co-ocurrencia
        g = df.groupby("fecha")["terminacion"].apply(lambda s: sorted(set(int(x) for x in s)))
        k = 2 if tipo == "pares" else 3
        counter: Counter = Counter()
        for _, nums in g.items():
            for combo in _combos(nums, k):
                counter[tuple(combo)] += 1
        for combo, freq in counter.most_common(top_k):
            combinaciones.append({
                "numeros": [f"{n:02d}" for n in combo],
                "frecuencia": int(freq),
            })
    elif tipo == "secuencias_dia":
        # Numero que sale a la cabeza en Matutino -> mismo dia en otro turno?
        # Pivotamos: filas=fecha, cols=turno, valores=terminacion.
        pivot = (
            df.pivot_table(
                index="fecha",
                columns="turno",
                values="terminacion",
                aggfunc="first",
            )
            .reset_index()
        )
        # Para cada turno NO matutino, los 10 numeros que MAS se repiten
        # entre Matutino y ese turno en el mismo dia.
        resultados: List[Dict] = []
        if "Matutino" in pivot.columns:
            for turno in [c for c in pivot.columns if c != "fecha" and c != "Matutino"]:
                pares = pivot[["Matutino", turno]].dropna()
                if len(pares) == 0:
                    continue
                res = []
                for m, v in pares.itertuples(index=False):
                    res.append((int(m), int(v)))
                # contando pares (matutino, otro_turno) iguales en distintos dias
                counter = Counter(res)
                for (a, b), freq in counter.most_common(top_k):
                    resultados.append({
                        "de_turno":   "Matutino",
                        "a_turno":    turno,
                        "de_numero":  f"{a:02d}",
                        "a_numero":   f"{b:02d}",
                        "frecuencia": int(freq),
                    })
        combinaciones = resultados

    return {
        "tipo": tipo,
        "combinaciones": combinaciones,
        "fuente_datos": fuente,
        "total_sorteos_analizados": int(len(df)),
    }


def _combos(iterable, k):
    """Yield all combinations of k elements from iterable, as ints."""
    iterable = list(iterable)
    n = len(iterable)
    if n < k:
        return
    indices = list(range(k))
    yield tuple(iterable[i] for i in indices)
    while True:
        stop = True
        for i in range(k - 1, -1, -1):
            if indices[i] != i + n - k:
                stop = False
                indices[i] += 1
                for j in range(i + 1, k):
                    indices[j] = indices[j - 1] + 1
                break
        if stop:
            return
        yield tuple(iterable[i] for i in indices)


# -------- Patrones estructura les --------

def construir_patrones() -> Dict:
    """Estadisticas estructurales: par/impar, decenas, suma tipica, sesgo."""
    df, fuente = cargar_historial()
    LOG.info("Patrones sobre %d sorteos.", len(df))
    if len(df) == 0:
        return {"fuente_datos": fuente, "total_sorteos_analizados": 0}

    terms = df["terminacion"].astype(int).to_numpy()
    pares_mask = terms % 2 == 0
    pares = int(pares_mask.sum())
    impares = int((~pares_mask).sum())

    decenas = ((terms // 10)).astype(int)
    dec_cnt = Counter(decenas.tolist())
    dec_dist = {f"{k*10:02d}-{k*10+9:02d}": int(v) for k, v in sorted(dec_cnt.items())}

    # Suma tipica por turno: usamos solo la terminacion (2 cifras) porque numero puede ser 4.
    sumas_2cifras = terms  # ya son 0..99

    return {
        "fuente_datos": fuente,
        "total_sorteos_analizados": int(len(df)),
        "pares_vs_impares": {
            "pares":   pares,
            "impares": impares,
            "ratio_pares": round(pares / max(1, len(terms)), 4),
        },
        "distribucion_por_decena": dec_dist,
        "rango_suma_terminacion": {
            "min":    int(sumas_2cifras.min()),
            "max":    int(sumas_2cifras.max()),
            "media":  round(float(sumas_2cifras.mean()), 2),
            "mediana": float(np.median(sumas_2cifras)),
        },
        "volatilidad_terminacion_desviacion": round(float(terms.std(ddof=0)), 3),
        "turno_mas_frecuente": str(df["turno"].value_counts().idxmax()) if len(df) else None,
        "turno_conteo": {
            str(k): int(v) for k, v in df["turno"].value_counts().items()
        },
    }
