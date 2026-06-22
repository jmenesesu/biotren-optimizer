"""Extrae salidas reales y automotor por servicio (PDF 2-410, dia laboral).

Cada pagina tiene DOS tablas apiladas (un sentido arriba, otro abajo), cada una
con su propia fila 'Tren'. Por eso se procesa por tabla: cada fila de origen se
empareja con la fila de servicios de su misma tabla (la fila 'Tren' inmediatamente
superior), y el automotor con esa misma tabla.

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

# estacion de origen por (linea, sentido)
ORIGEN = {("L2", "CC->CW"): "CONCEP", ("L2", "CW->CC"): "CORONEL",
          ("L1", "TH->LJ"): "MERCADO", ("L1", "LJ->TH"): "LAJA"}
PREF = {"CONCEP": ("L2", "CC->CW"), "CORONEL": ("L2", "CW->CC"),
        "MERCADO": ("L1", "TH->LJ"), "LAJA": ("L1", "LJ->TH"),
        "SAN ROSENDO": ("L1", "LJ->TH")}


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


def _es_tren_row(r):
    return len([w for w in r if SERV.fullmatch(w["text"])]) >= 5


def _servs(r):
    return sorted([(w["text"], (w["x0"] + w["x1"]) / 2) for w in r if SERV.fullmatch(w["text"])],
                  key=lambda x: x[1])


def _match_col(xc, servs, tol=30):
    s = min(servs, key=lambda v: abs(v[1] - xc))
    return s[0] if abs(s[1] - xc) < tol else None


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
    # filas 'Tren' con su y
    tren_rows = [(r[0]["top"], _servs(r)) for r in R if _es_tren_row(r)]
    tren_rows.sort()
    if not tren_rows:
        return []
    ys = [y for y, _ in tren_rows] + [1e9]

    out = []
    for ti, (ytren, servs) in enumerate(tren_rows):
        y0, y1 = ytren, ys[ti + 1]
        region = [r for r in R if y0 - 1 <= r[0]["top"] < y1]
        # unidad: fila con SFE/UT dentro de la region, cercana al Tren
        unidades = {}
        for r in region:
            if 0 < r[0]["top"] - ytren < 30:
                for i, w in enumerate(r):
                    if UNIDAD.fullmatch(w["text"]) and i + 1 < len(r) and NUMUN.fullmatch(r[i + 1]["text"]):
                        xc = (w["x0"] + r[i + 1]["x1"]) / 2
                        sv = _match_col(xc, servs, 35)
                        if sv:
                            unidades[sv] = f"{w['text']} {r[i+1]['text']}"
        # origen = primera estacion de la tabla (fila superior con horarios cuya
        # etiqueta coincide con un origen conocido de la linea). Evita tomar la
        # estacion DESTINO (que aparece al fondo de la misma tabla).
        prefijos = {p: sent for (p, (l, sent)) in PREF.items() if l == linea}
        cand = []
        for r in region:
            etiqueta = "".join(w["text"].upper() for w in r if w["x0"] < 150)
            pref = next((p for p in prefijos if etiqueta.startswith(p)), None)
            tiempos = [w for w in r if TIME.fullmatch(w["text"]) and w["x0"] > 150]
            if pref and tiempos:
                cand.append((r[0]["top"], prefijos[pref], tiempos))
        if not cand:
            continue
        cand.sort(key=lambda x: x[0])
        _, sent, tiempos = cand[0]          # la tabla superior = origen
        for t in tiempos:
            xc = (t["x0"] + t["x1"]) / 2
            sv = _match_col(xc, servs, 30)
            if sv:
                out.append({"linea": linea, "sentido": sent, "servicio": sv,
                            "salida_min": _hms(t["text"]), "unidad": unidades.get(sv, "")})
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
    print(f"Salidas: {len(df)} | con unidad: {(df['unidad']!='').sum()}")
    print(df.groupby(["linea", "sentido"])["servicio"].nunique().to_string())
    # chequeo: servicios que aparecen en ambos sentidos (no deberia haber)
    for linea in ["L2", "L1"]:
        g = df[df.linea == linea]
        dup = g[g.duplicated("servicio", keep=False)]
        print(f"{linea}: servicios en ambos sentidos = {dup['servicio'].nunique()} (debe ser 0)")
    print("\nEjemplo L2 CC->CW:", df[(df.linea=='L2')&(df.sentido=='CC->CW')]['servicio'].head(5).tolist())
    print("Ejemplo L2 CW->CC:", df[(df.linea=='L2')&(df.sentido=='CW->CC')]['servicio'].head(5).tolist())
