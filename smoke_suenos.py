"""Smoke determinístico del Oráculo de los Sueños."""
import json, sys
import suenos

casos = [
    ("abstracto 1 xyzqqq", "vacio emocional sin matches"),
    ("krypton volando con ballenas fosforescentes", "abstracto raro"),
    (u"uña sintética de mercurio", "abstracto caprichoso"),
    ("gato negro",                "matchea 05"),
]
out = []
for texto, _ in casos:
    r = suenos.construir_respuesta(texto)
    out.append({"texto": texto, "numeros": r["numeros"],
                "fuente0": r["detalles"][0]["fuente"] if r["detalles"] else None})

# Test de determinismo: mismo texto, mismo día → mismo número
import suenos as S1
r_hoy_a = S1.construir_respuesta("krypton volando con ballenas fosforescentes")
r_hoy_b = S1.construir_respuesta("krypton volando con ballenas fosforescentes")
# Y distinto al día siguiente, simulando:
from datetime import date, timedelta
manana = date.today() + timedelta(days=1)
r_manana = S1.construir_respuesta("krypton volando con ballenas fosforescentes", fecha=manana)

out.append({
    "test_idempotente_hoy": r_hoy_a["numeros"] == r_hoy_b["numeros"],
    "test_cambia_manana":   r_hoy_a["numeros"] != r_manana["numeros"],
    "hoy":  r_hoy_a["numeros"],
    "manana": r_manana["numeros"],
})

with open("smoke_suenos_out.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print("OK", file=sys.stderr)
