"""
Esquemas Pydantic de la API "Quiniela de Tucumán Inteligente: Mística & Datos".

Todos los endpoints devuelven JSON limpio, validado, y NUNCA un 500 al cliente.
"""
from __future__ import annotations

from datetime import date
from typing import Dict, List

from pydantic import BaseModel, Field


# ---------- /api/sorteos (resultados en vivo del día) ----------

class TurnosDelDia(BaseModel):
    """Cuatro turnos oficiales de la Quiniela Tucumana.
    Si un turno aún no se sorteó, el valor es '----'."""
    Matutina: str = Field(..., description="Primer premio 'A la cabeza' de la Matutina. '----' si aún no salió.")
    Electrica: str = Field(..., description="Primer premio 'A la cabeza' de la Eléctrica / Siesta.")
    Vespertina: str = Field(..., description="Primer premio 'A la cabeza' de la Vespertina.")
    Nocturna: str = Field(..., description="Primer premio 'A la cabeza' de la Nocturna.")


class SorteosDelDia(BaseModel):
    fecha: date
    turnos: TurnosDelDia
    fuente: str = Field(..., description="Origen de los datos: 'scraper', 'historico_csv' o 'mock_determinista'.")
    advertencia: str | None = Field(default=None, description="Mensaje cuando se usó fallback.")


# ---------- /api/estadisticas ----------

class NumeroFrecuente(BaseModel):
    numero: str = Field(..., description="Terminación de 2 cifras, '00' a '99'.")
    frecuencia: int = Field(..., ge=0)


class NumeroDemorado(BaseModel):
    numero: str = Field(..., description="Terminación de 2 cifras, '00' a '99'.")
    sorteos_sin_salir: int = Field(..., ge=0)


class Estadisticas(BaseModel):
    calientes: List[NumeroFrecuente]
    demorados: List[NumeroDemorado]
    turnos_del_dia: TurnosDelDia
    fuente_datos: str = Field(..., description="'historico_csv' o 'simulado_inicial'.")
    total_sorteos_analizados: int = Field(..., ge=0)


# ---------- /api/suenos (El Oráculo de los Sueños Tucumano) ----------

class CoincidenciaSueno(BaseModel):
    numero: str = Field(..., description="Número (00-99) asociado a la palabra del diccionario.")
    palabra_clave: str
    significado: str
    fuente: str = Field(default="diccionario", description="'diccionario' o 'hash_determinista'.")


class RespuestaSuenos(BaseModel):
    texto_normalizado: str
    fecha: date
    numeros: List[str] = Field(..., description="Hasta 3 números sugeridos, sin duplicados, ordenados.")
    detalles: List[CoincidenciaSueno]
    algoritmo: str = Field(..., description="Descripción humana de cómo se obtuvieron los números.")


# ---------- / y /api/health ----------

class Salud(BaseModel):
    estado: str = "ok"
    servicio: str = "Quiniela Tucumana - Mistica & Datos"
    version: str = "1.0.0"
    fecha: date


class Raiz(BaseModel):
    mensaje: str
    endpoints: Dict[str, str]
