"""Smoke test: ejecuta los módulos y vuelca resultados a smoke_out.json."""
import json
import sys

import scraper
import estadisticas
import suenos

sd = scraper.obtener_turnos_del_dia()
e = estadisticas.construir_estadisticas(
    {"Matutina": "----", "Electrica": "----", "Vespertina": "----", "Nocturna": "----"}
)
suenos_tests = [
    "soñe con un gato negro y encontre dinero",
    "visite un pueblo extraterrestre con mariposas fosforescentes",
    "ayer llovia y subi al cerro de tucuman",
    "me persiguio la policia y vi una virgen",
]
srs = [suenos.construir_respuesta(t) for t in suenos_tests]

out = {
    "scraper": sd,
    "estadisticas": {
        "calientes_top2": e["calientes"][:2],
        "demorados_top2": e["demorados"][:2],
        "total": e["total_sorteos_analizados"],
        "fuente": e["fuente_datos"],
    },
    "suenos": [
        {"texto": t, "numeros": r["numeros"], "fuente": r["detalles"][0]["fuente"]}
        for t, r in zip(suenos_tests, srs)
    ],
}
with open("smoke_out.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print("OK", file=sys.stderr)
