"""Extrae salidas reales y automotor asignado por servicio (PDF 2-410, dia laboral).

Por cada servicio: hora de salida en la estacion de origen (por sentido) y el
automotor asignado (SFE 1, SFE B1, UT 1, ...), leido de la fila bajo 'Tren'.

Salida:
    datos/clean/salidas_reales.csv  (linea, sentido, servicio, salida_min, unidad)
"""
import re
import sys
from pathlib import Path
import pandas as pd
import pdfplumber

sys.path.append(str(Path(__file__).resolve().parent))
from config import ITIN_DIR, CLEAN  # noqa: E402

PDF = ITIN_DIR / "2-410. Itinerario Pasajeros Concepción 30-mar-2026.pdf"
TIME = re.compile(r"^\d{1,2}:\d{2}$")
SERV = re.compile(r"^20\d{3}$")
UNIDAD = re.compile(r"^(SFE|UT)$")
NUMUN = re.compile(r"^(B?\d{1,2})$")

ORIGEN = {("L2", "CC->CW"): "CONCEP", ("L2", "CW->CC"): "CORONEL",
          ("L1", "TH->LJ"): "MERCADO", ("L1", "LJ->TH"): "LAJA"}


def _hms(t):
    h, m = t.split(":")[:2]
    return int(h) * 60 + int(m)


def _rows(words, tol=3):
    R = []
    for w in sorted(words, key=lambda w: w["top"]):
        for r in R:
            if abs(r[0]["top"] - w["top"]) <= tol:
                r.append(w); break
        else:
            R.append([w])
    for r in R:
        r.sort(key=lambda w: w["x0"])
    return R


def _serv_row(R):
    return max(R, key=lambda r: len([w for w in r if SERV.fullmatch(w["text"])]))


def _servicios(R):
    sr = _serv_row(R)
    return sorted([(w["text"], (w["x0"] + w["x1"]) / 2) for w in sr if SERV.fullmatch(w["text"])],
                  key=lambda x: x[1]), sr[0]["top"]


def _unidades(R, sy, servs):
    """Empareja unidad (SFE n / UT n) con el servicio por columna."""
    out = {}
    for r in R:
        if not (0 < r[0]["top"] - sy < 30):
            continue
        toks = r
        for i, w in enumerate(toks):
            if UNIDAD.fullmatch(w["text"]) and i + 1 < len(toks) and NUMUN.fullmatch(toks[i + 1]["text"]):
                etiqueta = f"{w['text']} {toks[i+1]['text']}"
                xc = (w["x0"] + toks[i + 1]["x1"]) / 2
                serv = min(servs, key=lambda s: abs(s[1] - xc))
                if abs(serv[1] - xc) < 35:
                    out[serv[0]] = etiqueta
    return out


def _salidas_pagina(pg, linea):
    words = pg.extract_words()
    texto = " ".join(w["text"] for w in words)
    if "Sábado" in texto or "Domingo" in texto:
        return []
    if linea == "L2" and "CONCEPCIÓN-CORONEL" not in texto:
        return []
    if linea == "L1" and "LAJA-TALCAHUANO" not in texto:
        return []
    R = _rows(words)
    servs, sy = _servicios(R)
    if not servs:
        return []
    unidades = _unidades(R, sy, servs)
    out = []
    for (l, sent), origen in ORIGEN.items():
        if l != linea:
            continue
        for r in R:
            etiqueta = "".join(w["text"].upper() for w in r if w["x0"] < 150)
            if not etiqueta.startswith(origen):
                continue
            for t in [w for w in r if TIME.fullmatch(w["text"]) and w["x0"] > 150]:
                xc = (t["x0"] + t["x1"]) / 2
                serv = min(servs, key=lambda s: abs(s[1] - xc))
                if abs(serv[1] - xc) < 30:
                    out.append({"linea": linea, "sentido": sent, "servicio": serv[0],
                                "salida_min": _hms(t["text"]),
                                "unidad": unidades.get(serv[0], "")})
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
    print(f"Salidas: {len(df)} | con unidad asignada: {(df['unidad']!='').sum()}")
    print(df.groupby(["linea", "sentido"])["servicio"].count().to_string())
    print("\nUnidades distintas:", sorted(u for u in df['unidad'].unique() if u))
    print("\nEjemplo L2 CC->CW:")
    print(df[(df.linea=='L2')&(df.sentido=='CC->CW')][['servicio','salida_min','unidad']].head(8).to_string(index=False))
