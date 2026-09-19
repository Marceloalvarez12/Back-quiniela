"""Genera un historico.csv fresco con 5 turnos/dia x 150 dias usando el
generador deterministico de data_loader. Ejecutar una vez.
"""
import sys
sys.path.insert(0, "D:\\Quiniela\\Back-quiniela")
from data_loader import write_initial_csv_if_missing, CSV_PATH
write_initial_csv_if_missing()
import csv
rows = list(csv.open and csv.reader(open(CSV_PATH, "r", encoding="utf-8"))) if False else None
with open(CSV_PATH, "r", encoding="utf-8") as f:
    count = sum(1 for _ in f) - 1
print(f"OK -> {CSV_PATH} ({count} filas)")
