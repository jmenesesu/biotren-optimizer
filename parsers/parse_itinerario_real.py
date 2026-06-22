"""Extrae las salidas reales por servicio del itinerario vigente (PDF 2-410).

Para las paginas de DIA LABORAL (Lun-Vie) de L2 y L1, lee la fila de la estacion
de origen de cada sentido y empareja cada hora de salida con su numero de
servicio por posicion de columna (coordenadas pdfplumber).

Salida:
    datos/clean/salidas_reales.csv  (linea, sentido, servicio, salida_min)
"""
import re
import sys
from pathlib import Path
import pandas as pd
import pdfplumber

sys.path.append(str(Path(__file__).resolve().parent))
from config import ITIN_DIR, CLEAN  # noqa: E402

PDF = ITIN_DIR / "2-410. Itinerario Pasajeros Concepción 30-mar-2026.pdf"
TIME = re.compile(r"^\d{1,2}:\d{2}$")          # solo H:MM (no H:MM:SS, que son tiempos de viaje)
SERV = re.compile(r"^20\d{3}$")

# Estacion de origen por linea y sentido (donde se lee la hora de salida)
ORIGEN = {
    ("L2", "CC->CW"): "CONCEP", ("L2", "CW->CC"): "CORONEL",
    ("L1", "TH->LJ"): "MERCADO", ("L1", "LJ->TH"): "LAJA",
}


def _hms(t):
    h, m = t.split(":")[:2]
    return int(h) * 60 + int(m)


def _rows(words, tol=3):
    rows = []
    for w in sorted(words, key=lambda w: w["top"]):
        for r in rows:
            if abs(r[0]["top"] - w["top"]) <= tol:
                r.append(w); break
        else:
            rows.append([w])
    return rows


def _servicios_fila(rows):
    """Devuelve [(servicio, x_centro)] de la fila 'Tren' (la de mas numeros 20xxx)."""
    best = []
    for r in rows:
        s = [(w["text"], (w["x0"] + w["x1"]) / 2) for w in r if SERV.fullmatch(w["text"])]
        if len(s) > len(best):
            best = s
    return sorted(best, key=lambda x: x[1])


def _salidas_pagina(pg, linea):
    words = pg.extract_words()
    texto = " ".join(w["text"] for w in words)
    if "Sábado" in texto or "Domingo" in texto:
        return []                     # solo dia laboral
    if linea == "L2" and "CONCEPCIÓN-CORONEL" not in texto:
        return []
    if linea == "L1" and "LAJA-TALCAHUANO" not in texto:
        return []
    servs = _servicios_fila(_rows(words))
    if not servs:
        return []
    out = []
    for (l, sent), origen in ORIGEN.items():
        if l != linea:
            continue
        # filas cuyo primer token (x pequeño) es la estacion de origen
        for r in _rows(words):
            etiqueta = "".join(w["text"].upper() for w in r if w["x0"] < 150)
            if not etiqueta.startswith(origen):
                continue
            tiempos = [w for w in r if TIME.fullmatch(w["text"]) and w["x0"] > 150]
            for t in tiempos:
                xc = (t["x0"] + t["x1"]) / 2
                serv = min(servs, key=lambda s: abs(s[1] - xc))
                if abs(serv[1] - xc) < 30:        # dentro de la columna
                    out.append({"linea": linea, "sentido": sent,
                                "servicio": serv[0], "salida_min": _hms(t["text"])})
    return out


def parse():
    filas = []
    with pdfplumber.open(PDF) as pdf:
        for pg in pdf.pages:
            for linea in ["L2", "L1"]:
                filas += _salidas_pagina(pg, linea)
    df = pd.DataFrame(filas).drop_duplicates(subset=["linea", "sentido", "servicio"])
    df = df.sort_values(["linea", "sentido", "salida_min"]).reset_index(drop=True)
    df.to_csv(CLEAN / "salidas_reales.csv", index=False)
    return df


if __name__ == "__main__":
    df = parse()
    print(f"Salidas reales extraidas: {len(df)}")
    print(df.groupby(["linea", "sentido"])["servicio"].count().to_string())
    print("\nEjemplo L2 CC->CW (primeras):")
    print(df[(df.linea == "L2") & (df.sentido == "CC->CW")].head(8).to_string(index=False))
