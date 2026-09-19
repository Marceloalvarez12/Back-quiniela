"""
Quiniela de Tucumán Inteligente: Mística & Datos — Backend FastAPI.

Ejecución:
    uvicorn app:app --host 0.0.0.0 --port 8000 --reload
    # o, equivalentemente:
    python app.py
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from data_loader import TURNOS, write_initial_csv_if_missing
from estadisticas import construir_estadisticas
from modelos import (
    Estadisticas,
    Raiz,
    RespuestaSuenos,
    Salud,
    SorteosDelDia,
    TurnosDelDia,
)
from prediccion import construir_combinaciones, construir_patrones, construir_prediccion
from scraper import obtener_turnos_del_dia
from suenos import construir_respuesta

# ---------- Logging ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
LOG = logging.getLogger("quiniela")


# ---------- Lifespan ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: crear CSV inicial si no existe.
    write_initial_csv_if_missing()
    LOG.info("Backend Quiniela Tucumán iniciado.")
    yield
    LOG.info("Backend Quiniela Tucumán finalizado.")


# ---------- App ----------
app = FastAPI(
    title="Quiniela de Tucumán Inteligente: Mística & Datos",
    version="1.0.0",
    description=(
        "API REST que combina extracción en vivo, estadísticas y folklore "
        "para la Quiniela Tucumana. CORS abierto para consumo desde v0/Vercel."
    ),
    lifespan=lifespan,
)

# ---------- CORS ----------
# Frontend v0/Vercel puede venir de cualquier origen → abrimos todo.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # con "*" no se pueden permitir credentials
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Endpoints ----------
@app.get("/", response_model=Raiz, tags=["meta"])
def raiz() -> Raiz:
    return Raiz(
        mensaje="Quiniela de Tucumán Inteligente: Mística & Datos — Backend activo.",
        endpoints={
            "salud":            "/api/health",
            "sorteos_del_dia":  "/api/sorteos",
            "estadisticas":     "/api/estadisticas",
            "prediccion":       "/api/prediccion",
            "combinaciones":    "/api/combinaciones",
            "patrones":         "/api/patrones",
            "suenos_GET":       "/api/suenos?texto=...",
            "docs":             "/docs",
            "openapi":          "/openapi.json",
        },
    )


@app.get("/api/health", response_model=Salud, tags=["meta"])
def salud() -> Salud:
    return Salud(fecha=date.today())


@app.get("/api/sorteos", response_model=SorteosDelDia, tags=["datos"])
def sorteos_del_dia() -> SorteosDelDia:
    """Resultados del día para los 4 turnos oficiales tucumanos."""
    try:
        data = obtener_turnos_del_dia()
    except Exception as e:
        # Defensa adicional: si TODO falla, devolvemos '----' igualmente.
        LOG.exception("Fallo absoluto en scraper: %s", e)
        data = {
            "turnos": {t: "----" for t in TURNOS},
            "fuente": "error_controlado",
            "advertencia": "Fallo inesperado controlado por la API (no se expuso 500).",
        }
    turnos = data["turnos"]
    return SorteosDelDia(
        fecha=date.today(),
        turnos=TurnosDelDia(
            Matutino=turnos.get("Matutino", "----"),
            Vespertino=turnos.get("Vespertino", "----"),
            Siesta=turnos.get("Siesta", "----"),
            Nocturno=turnos.get("Nocturno", "----"),
            Extra=turnos.get("Extra", "----"),
        ),
        fuente=data["fuente"],
        advertencia=data.get("advertencia"),
    )


@app.get("/api/estadisticas", response_model=Estadisticas, tags=["analisis"])
def estadisticas() -> Estadisticas:
    """Top 5 calientes + top 5 demorados del historial."""
    # Traemos también los turnos del día para enriquecer la respuesta.
    try:
        sorteos = obtener_turnos_del_dia()
        turnos_hoy = sorteos.get("turnos") or {t: "----" for t in TURNOS}
    except Exception as e:
        LOG.exception("Fallo al obtener turnos del día para /api/estadisticas: %s", e)
        turnos_hoy = {t: "----" for t in TURNOS}

    try:
        data = construir_estadisticas(
            turnos_del_dia=turnos_hoy,
        )
    except Exception as e:
        LOG.exception("Fallo estadístico controlado: %s", e)
        # Aún si Pandas falla, devolvemos esqueletos válidos.
        tur = TurnosDelDia(
            Matutino="----", Vespertino="----", Siesta="----", Nocturno="----", Extra="----"
        )
        return Estadisticas(
            calientes=[
                {"numero": "00", "frecuencia": 0},
                {"numero": "00", "frecuencia": 0},
                {"numero": "00", "frecuencia": 0},
                {"numero": "00", "frecuencia": 0},
                {"numero": "00", "frecuencia": 0},
            ],
            demorados=[
                {"numero": "00", "sorteos_sin_salir": 0},
                {"numero": "00", "sorteos_sin_salir": 0},
                {"numero": "00", "sorteos_sin_salir": 0},
                {"numero": "00", "sorteos_sin_salir": 0},
                {"numero": "00", "sorteos_sin_salir": 0},
            ],
            turnos_del_dia=tur,
            fuente_datos="error_controlado",
            total_sorteos_analizados=0,
        )

    return Estadisticas(
        calientes=data["calientes"],
        demorados=data["demorados"],
        turnos_del_dia=TurnosDelDia(**data["turnos_del_dia"]),
        fuente_datos=data["fuente_datos"],
        total_sorteos_analizados=data["total_sorteos_analizados"],
    )


@app.get("/api/suenos", response_model=RespuestaSuenos, tags=["folklore"],
         summary="El Oráculo de los Sueños Tucumano (sin tilde)")
def suenos(texto: str = Query(..., min_length=1, max_length=600,
                              description="Relato del sueño del usuario.")) -> RespuestaSuenos:
    """El Oráculo de los Sueños Tucumano: devuelve hasta 3 números sugeridos
    más su significado y la fuente (diccionario o hash determinista)."""
    if texto is None or not texto.strip():
        raise HTTPException(status_code=400, detail="El parámetro 'texto' es obligatorio.")
    data = construir_respuesta(texto)
    return RespuestaSuenos(**data)


# Alias con la "ñ" exacta que usa el frontend v0 (acentos en URL son válidos).
@app.get("/api/sueños", response_model=RespuestaSuenos, tags=["folklore"],
         summary="El Oráculo de los Sueños Tucumano (alias con ñ — v0)")
def suenos_con_enye(texto: str = Query(..., min_length=1, max_length=600,
                                       description="Relato del sueño del usuario.")) -> RespuestaSuenos:
    """Alias con 'ñ' que matchea 1:1 la URL que el componente v0 está pegando.
    Devuelve exactamente la misma respuesta que `/api/suenos`."""
    if texto is None or not texto.strip():
        raise HTTPException(status_code=400, detail="El parámetro 'texto' es obligatorio.")
    data = construir_respuesta(texto)
    return RespuestaSuenos(**data)


# ---------- Prediccion / Combinaciones / Patrones ----------

@app.get("/api/prediccion", tags=["analisis"],
         summary="Top 10 numeros sugeridos (heuristica RECREATIVA)")
def prediccion(
    turno: str | None = Query(None, description="Filtrar a un turno (Matutino, Vespertino, Siesta, Nocturno, Extra)."),
    k: int = Query(10, ge=1, le=50, description="Cantidad del top."),
    ventana: int = Query(30, ge=5, le=200, description="Sorteos para 'calor_reciente'."),
    pesos: str | None = Query(None,
                              description='JSON override de pesos, ej {"s1_calor_reciente":3.0}, null usa DEFAULT'),
):
    """Heuristica de ranking basada en 6 senales historicas.
    NO ASEGURA PROBABILIDAD: cada terminacion 00..99 sigue siendo 1/100 real.
    Sirve para jugar responsablemente con criterio."""
    from prediccion import _parse_pesos
    return construir_prediccion(
        turno=turno,
        pesos=_parse_pesos(pesos),
        top_k=k,
        ventana_reciente=ventana,
    )


@app.get("/api/combinaciones", tags=["analisis"],
         summary="Combinaciones historicamente frecuentes")
def combinaciones(
    tipo: str = Query("pares", description="pares | trios | secuencias_dia"),
    k: int = Query(10, ge=1, le=50),
):
    """`pares` y `trios`: combinaciones que suelen aparecer juntas en un mismo dia.
    `secuencias_dia`: 'si en Matutino salio X, en Vespertino/Siesta/Nocturno/Extra
    salio Y' con la frecuencia historica."""
    return construir_combinaciones(tipo=tipo, top_k=k)


@app.get("/api/patrones", tags=["analisis"],
         summary="Patrones estructurales: par/impar, decenas, sesgo")
def patrones():
    return construir_patrones()


# ---------- Arranque directo ----------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,           # para debug local pasalo a True
        log_level="info",
    )
