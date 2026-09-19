"""
El Oráculo de los Sueños Tucumano — endpoint /api/suenos.

Diccionario basado en la TABLA CLÁSICA DE LOS SUEÑOS de la quiniela
argentina (folklore compartido con las loterías de Buenos Aires, Córdoba,
Santa Fe y Tucumán). Más de 50 entradas explícitas.

Lógica de procesamiento:
  1) Normaliza el texto del usuario (minúsculas + trim).
  2) Busca coincidencias de palabras/frases del diccionario dentro del sueño.
     Si encuentra → devuelve hasta 3 números asociados (los más fuertes
     primero), junto con su significado.
  3) Si NO encuentra NINGUNA coincidencia (sueño abstracto), genera 2 números
     deterministas vía SHA-256(texto + fecha). Mismo texto + mismo día =
     mismo número (durante todo el día); cambia al día siguiente.

Esto evita que el cliente reciba 404/500 cuando el usuario escribe cualquier
locura (visiones, palabras inventadas, etc.).
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date
from typing import Dict, List

LOG = logging.getLogger("quiniela.suenos")


# ---------- Diccionario de los sueños (00..99) ----------
# 50+ entradas del folklore tradicional de la quiniela tucumana/argentina.
# Formato: numero -> {"significado": "...", "palabras": [keyword1, ...]}.
#
# Las 'palabras' cubren sinónimos y formas declinadas para que la búsqueda
# simple por substring ("gato" también casará con "gatos", "gata", etc.).
# Para matching perfecto en plurales, normalizamos arriba.

SUENOS: Dict[str, Dict] = {
    "00": {"significado": "Los huevos",                 "palabras": ["huevo", "huevos"]},
    "01": {"significado": "El agua",                    "palabras": ["agua", "aguas", "rio", "río", "mar", "lluvia"]},
    "02": {"significado": "El niño / La niña",          "palabras": ["niño", "niña", "nene", "nena", "bebe", "bebé", "infante"]},
    "03": {"significado": "El padre / La madre",        "palabras": ["padre", "madre", "papa", "papá", "mama", "mamá"]},
    "04": {"significado": "El gabinete / La oficina",   "palabras": ["gabinete", "oficina", "escritorio"]},
    "05": {"significado": "El gato",                    "palabras": ["gato", "gata", "gatos"]},
    "06": {"significado": "El perro",                   "palabras": ["perro", "perra", "perros", "cachorro"]},
    "07": {"significado": "El revólver / La pistola",   "palabras": ["pistola", "revolver", "revólver", "arma"]},
    "08": {"significado": "La virgen / María",          "palabras": ["virgen", "maria", "maría", "santa"]},
    "09": {"significado": "El arroyo",                  "palabras": ["arroyo", "riacho", "canal"]},
    "10": {"significado": "La leche",                   "palabras": ["leche", "mamadera"]},
    "11": {"significado": "Los ojos / Las lentes",      "palabras": ["ojo", "ojos", "lente", "lentes", "anteojo", "anteojos"]},
    "12": {"significado": "La serpiente / La víbora",   "palabras": ["serpiente", "vibora", "víbora", "culebra"]},
    "13": {"significado": "La boca / Los labios",       "palabras": ["boca", "labios", "labio", "lengua"]},
    "14": {"significado": "El borracho / La borracha",  "palabras": ["borracho", "borracha", "embriago", "ebrio"]},
    "15": {"significado": "El niño muerto",             "palabras": ["nino muerto", "angeles", "ángel", "angel", "angelito"]},
    "16": {"significado": "El anillo / La sortija",     "palabras": ["anillo", "sortija", "alianza"]},
    "17": {"significado": "La desgracia",               "palabras": ["desgracia", "mala suerte", "desdicha", "contratiempo"]},
    "18": {"significado": "La sangre",                  "palabras": ["sangre", "hemorragia", "herida"]},
    "19": {"significado": "La mesa / La comida",        "palabras": ["mesa", "comida", "cena", "almuerzo", "asado"]},
    "20": {"significado": "El casino / La fiesta",      "palabras": ["casino", "fiesta", "baile", "baile"]},
    "21": {"significado": "La mujer",                   "palabras": ["mujer", "dama", "esposa", "novia"]},
    "22": {"significado": "El loco / La loca",          "palabras": ["loco", "loca", "demente", "manicomio"]},
    "23": {"significado": "El espejo",                  "palabras": ["espejo", "reflejo"]},
    "24": {"significado": "La iglesia / El cura",       "palabras": ["iglesia", "cura", "parroco", "párroco", "sacerdote", "capilla"]},
    "25": {"significado": "La gallina / El gallo",      "palabras": ["gallina", "gallo", "gallinas"]},
    "26": {"significado": "La misa / Comunión",         "palabras": ["misa", "comunion", "comunión", "ostia", "hostia"]},
    "27": {"significado": "Las piernas / Los pies",     "palabras": ["pierna", "piernas", "pie", "pies"]},
    "28": {"significado": "La herradura",               "palabras": ["herradura", "herraje"]},
    "29": {"significado": "El santo / San José",        "palabras": ["santo", "san jose", "san josé"]},
    "30": {"significado": "La luz / La vela",           "palabras": ["luz", "vela", "lampara", "lámpara"]},
    "31": {"significado": "La ramera / La prostituta",  "palabras": ["ramera", "prostituta", "puta"]},
    "32": {"significado": "El dinero",                  "palabras": ["dinero", "plata", "billete", "pesos", "efectivo"]},
    "33": {"significado": "La cruz / El crucifijo",     "palabras": ["cruz", "crucifijo", "calvario"]},
    "34": {"significado": "La cabeza",                  "palabras": ["cabeza", "craneo", "cráneo"]},
    "35": {"significado": "La tijera",                  "palabras": ["tijera", "tijeras"]},
    "36": {"significado": "El médico / El doctor",      "palabras": ["medico", "médico", "doctor", "doctora"]},
    "37": {"significado": "El diente / La muela",       "palabras": ["diente", "muela", "dentista"]},
    "38": {"significado": "El pan",                     "palabras": ["pan", "panaderia", "panadería"]},
    "39": {"significado": "La cocina / El cocinero",    "palabras": ["cocina", "cocinero", "cocinera"]},
    "40": {"significado": "La牛乳/El toro",            "palabras": ["toro", "vaca", "vaches"]},  # placeholder; ver 41
    "41": {"significado": "El toro / La vaca",          "palabras": ["toro", "vaca", "novillo", "ternero"]},
    "42": {"significado": "La montaña / El cerro",     "palabras": ["montaña", "cerro", "sierra", "cerros", "tucuman"]},
    "43": {"significado": "El caballo / La yegua",      "palabras": ["caballo", "yegua", "potro"]},
    "44": {"significado": "La lombriz / La culebra",    "palabras": ["lombriz", "gusano"]},
    "45": {"significado": "El limón / La naranja",      "palabras": ["limon", "limón", "naranja", "citrus"]},
    "46": {"significado": "El hospital / La clínica",   "palabras": ["hospital", "clinica", "clínica", "enfermeria"]},
    "47": {"significado": "La ventana / La puerta",     "palabras": ["ventana", "puerta"]},
    "48": {"significado": "El muerto / El entierro",   "palabras": ["muerto", "muerte", "funeral", "entierro", "cadaver", "cadáver"]},
    "49": {"significado": "La camisa / La ropa",        "palabras": ["camisa", "ropa", "vestido", "traje"]},
    "50": {"significado": "El balcón",                  "palabras": ["balcon", "balcón"]},
    "51": {"significado": "La guitarra / El bandoneón", "palabras": ["guitarra", "bandoneon", "bandoneón", "chacarera"]},
    "52": {"significado": "La procesión",               "palabras": ["procesion", "procesión"]},
    "53": {"significado": "La fiebre",                  "palabras": ["fiebre", "calentura"]},
    "54": {"significado": "La naranja",                 "palabras": ["naranja"]},
    "55": {"significado": "El loro / El papagayo",      "palabras": ["loro", "papagayo"]},
    "56": {"significado": "La merienda",                "palabras": ["merienda", "mate"]},
    "57": {"significado": "La mudanza",                 "palabras": ["mudanza", "mudarse"]},
    "58": {"significado": "El azahar / Las flores",     "palabras": ["azahar", "flores", "flor"]},
    "59": {"significado": "La pobreza",                 "palabras": ["pobreza", "pobre", "miseria"]},
    "60": {"significado": "El pensamiento",             "palabras": ["pensamiento", "recuerdo"]},
    "61": {"significado": "La llave",                   "palabras": ["llave", "cerradura"]},
    "62": {"significado": "El cilindro / El cañón",     "palabras": ["canon", "cañón", "cilindro"]},
    "63": {"significado": "El combate / La pelea",      "palabras": ["combate", "pelea", "riña", "lucha"]},
    "64": {"significado": "El martillo",                "palabras": ["martillo"]},
    "65": {"significado": "La paloma",                  "palabras": ["paloma", "palomas"]},
    "66": {"significado": "La caída",                   "palabras": ["caida", "caída", "tropiezo"]},
    "67": {"significado": "El mono",                    "palabras": ["mono", "monos"]},
    "68": {"significado": "El ladrón / El robo",        "palabras": ["ladron", "ladrón", "robo", "ratero"]},
    "69": {"significado": "Los huesos",                 "palabras": ["hueso", "huesos"]},
    "70": {"significado": "La cosecha",                 "palabras": ["cosecha", "cosechar"]},
    "71": {"significado": "El médico — urgencia",       "palabras": ["urgencia", "emergencia"]},
    "72": {"significado": "El cirujano",                "palabras": ["cirujano", "cirugia", "cirugía"]},
    "73": {"significado": "Los amigos",                 "palabras": ["amigo", "amiga", "amigos"]},
    "74": {"significado": "La tumba / La sepultura",    "palabras": ["tumba", "sepultura", "sepulcro"]},
    "75": {"significado": "El abrazo",                  "palabras": ["abrazo"]},
    "76": {"significado": "El sol",                     "palabras": ["sol", "rayo"]},
    "77": {"significado": "La virgen del Valle (Tucumán)", "palabras": ["valle", "virgen del valle"]},
    "78": {"significado": "La mano",                    "palabras": ["mano", "manos"]},
    "79": {"significado": "La deuda",                   "palabras": ["deuda", "deudas"]},
    "80": {"significado": "El libro",                   "palabras": ["libro", "libros"]},
    "81": {"significado": "La ventana rota",            "palabras": ["vidrio", "ventana rota"]},
    "82": {"significado": "El carbón",                  "palabras": ["carbon", "carbón"]},
    "83": {"significado": "El incendio",                "palabras": ["incendio", "fuego", "llamas"]},
    "84": {"significado": "La pintura",                 "palabras": ["pintura", "cuadro", "pintor"]},
    "85": {"significado": "La nube",                    "palabras": ["nube", "nubes"]},
    "86": {"significado": "Elguitarra segunda",        "palabras": ["violin", "violín", "violinista"]},
    "87": {"significado": "La escalera",                "palabras": ["escalera", "escaleras"]},
    "88": {"significado": "El beso",                    "palabras": ["beso", "besos"]},
    "89": {"significado": "La culebra — peligro",       "palabras": ["peligro", "amenaza"]},
    "90": {"significado": "El cielo",                   "palabras": ["cielo", "estrellas"]},
    "91": {"significado": "El cartero",                 "palabras": ["cartero", "carta", "cartas", "correo"]},
    "92": {"significado": "El vodka / La bebida fuerte","palabras": ["vodka", "whisky", "bebida fuerte"]},
    "93": {"significado": "El paraguas",                "palabras": ["paraguas"]},
    "94": {"significado": "El espejo roto",             "palabras": ["espejo roto"]},
    "95": {"significado": "El zapato",                  "palabras": ["zapato", "zapatos", "botas"]},
    "96": {"significado": "La araña",                   "palabras": ["araña", "arana"]},
    "97": {"significado": "La guitarra rota",           "palabras": ["guitarra rota"]},
    "98": {"significado": "La radio / La música",       "palabras": ["radio", "musica", "música"]},
    "99": {"significado": "El general / El poder",      "palabras": ["general", "militar", "poder"]},
}


def _normalizar(texto: str) -> str:
    return (texto or "").strip().lower()


def _hash_a_numero(texto: str, fecha: date, offset: int) -> int:
    """Devuelve un entero 0..99 derivado deterministamente del hash del texto+fecha."""
    payload = f"{texto}|{fecha.isoformat()}|{offset}".encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    # Tomamos los primeros 8 hex chars como int.
    return int(digest[:8], 16) % 100


def interpretar_sueno(texto: str, fecha: date | None = None) -> Dict:
    """Procesa el texto del usuario y devuelve el dict de respuesta."""
    fecha = fecha or date.today()
    norm = _normalizar(texto)
    LOG.info("Sueño recibido (fecha=%s, len=%d): %r", fecha, len(norm), norm[:120])

    if not norm:
        # Texto vacío → fallback determinista con texto vacío igualmente.
        n1 = _hash_a_numero("", fecha, 0)
        n2 = _hash_a_numero("", fecha, 1)
        return {
            "texto_normalizado": norm,
            "fecha": fecha.isoformat(),
            "numeros": sorted({f"{n1:02d}", f"{n2:02d}"}),
            "detalles": [
                {
                    "numero": f"{n1:02d}",
                    "palabra_clave": "",
                    "significado": "Número generado por oráculo determinista (sin texto).",
                    "fuente": "hash_determinista",
                }
            ],
            "algoritmo": (
                "Texto vacío. Se aplican 2 números calculados con SHA-256(fecha) "
                "para que el oráculo nunca falle."
            ),
        }

    # 1) Búsqueda por diccionario.
    detalles: List[Dict] = []
    numeros_set: set[str] = set()
    for num, info in SUENOS.items():
        for kw in info["palabras"]:
            if kw in norm:
                # Evitar duplicados si una keyword matchea la misma entrada.
                if num in numeros_set:
                    continue
                numeros_set.add(num)
                detalles.append({
                    "numero": num,
                    "palabra_clave": kw,
                    "significado": info["significado"],
                    "fuente": "diccionario",
                })
                break  # una keyword por entrada alcanza

    if detalles:
        # Orden: priorizamos los números "más fuertes" (0-9) primero,
        # luego los pares, etc. Para determinismo: ordenar por número asc.
        detalles.sort(key=lambda d: int(d["numero"]))
        numeros = sorted(numeros_set)
        # Si hay menos de 3, rellenamos con 1 hash para llegar al menos a 3.
        while len(numeros) < 3:
            extra = f"{_hash_a_numero(norm, fecha, len(numeros)):02d}"
            if extra not in numeros_set:
                numeros.append(extra)
                numeros_set.add(extra)
        return {
            "texto_normalizado": norm,
            "fecha": fecha.isoformat(),
            "numeros": numeros[:3],
            "detalles": detalles[:3],
            "algoritmo": (
                "Coincidencias encontradas en el diccionario folclórico; "
                "si hubo menos de 3, se completó con hash determinista(sha256)."
            ),
        }

    # 2) Sin coincidencias → 2 números deterministas (cambian cada día, repetibles hoy).
    n1 = _hash_a_numero(norm, fecha, 0)
    n2 = _hash_a_numero(norm, fecha, 1)
    # Si por colisión de módulo n1 == n2, generamos un tercer slot.
    if n1 == n2:
        n2 = _hash_a_numero(norm, fecha, 2)
    numeros = sorted({f"{n1:02d}", f"{n2:02d}"})
    return {
        "texto_normalizado": norm,
        "fecha": fecha.isoformat(),
        "numeros": numeros,
        "detalles": [
            {
                "numero": f"{n1:02d}",
                "palabra_clave": "<hash>",
                "significado": (
                    "Número generado por el Oráculo (SHA-256 del texto + fecha). "
                    "Repetible el día de hoy."
                ),
                "fuente": "hash_determinista",
            },
            {
                "numero": f"{n2:02d}",
                "palabra_clave": "<hash>",
                "significado": (
                    "Número generado por el Oráculo (SHA-256 del texto + fecha). "
                    "Repetible el día de hoy."
                ),
                "fuente": "hash_determinista",
            },
        ],
        "algoritmo": (
            "Sin coincidencias con el diccionario. Se generan 2 números "
            "deterministas vía SHA-256(texto|fecha): cambian cada día pero "
            "son estables durante toda la jornada."
        ),
    }


def construir_respuesta(texto: str, fecha: date | None = None) -> Dict:
    """Wrapper con logging explícito (se registra cada consulta)."""
    LOG.info("Consulta de sueño: texto=%r", texto)
    try:
        r = interpretar_sueno(texto, fecha=fecha)
        LOG.info("Sueño procesado: numeros=%s", r["numeros"])
        return r
    except Exception as e:
        # Plan C: nunca fallar al cliente.
        LOG.exception("Error inesperado procesando sueño: %s", e)
        f = fecha or date.today()
        n = _hash_a_numero(texto or "", f, 99)
        return {
            "texto_normalizado": _normalizar(texto),
            "fecha": f.isoformat(),
            "numeros": [f"{n:02d}"],
            "detalles": [
                {
                    "numero": f"{n:02d}",
                    "palabra_clave": "<hash-emergencia>",
                    "significado": "Oráculo en modo emergencia (hash).",
                    "fuente": "hash_determinista",
                }
            ],
            "algoritmo": "Recuperación de emergencia: hash determinista.",
        }
