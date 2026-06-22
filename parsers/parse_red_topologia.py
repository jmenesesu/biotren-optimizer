"""Topologia esquematica de la red (OTML), separada por corredor en bandas.

Cada corredor de OpenTrack usa su propio espacio de coordenadas, por lo que se
superponen. Aqui se identifica el corredor por el prefijo del id de cada nodo y
se apilan en bandas verticales para un esquema legible (cada banda = un corredor,
mostrando su trazado: vias paralelas, desvios, cruzamientos).

Salida:
    datos/clean/red_arcos.csv      (corredor, x, y) por segmento (x1,y1,x2,y2 ya en bandas)
    datos/clean/red_estaciones.csv (corredor, label, x, y)
"""
import re
import sys
from pathlib import Path
import pandas as pd
from lxml import etree

sys.path.append(str(Path(__file__).resolve().parent))
from config import INFRA_DIR, CLEAN  # noqa: E402

OTML = INFRA_DIR / "Export Infraestructure Data (OTML-Format).xml"
# Corredores relevantes y su orden (etiqueta legible)
ORDEN_CORR = ["K-06-EZ-TH_1", "K05-CC", "K-04-OH-ZW-CV_1", "K03-QU-HQ",
              "K02-TL-UN", "K01-BU-GO", "L01-BB-LM", "L02-ES-CW", "L03-LT-IV"]
NOMBRE_CORR = {
    "K-06-EZ-TH_1": "El Arenal–Mercado", "K05-CC": "Concepción",
    "K-04-OH-ZW-CV_1": "Chiguayante–La Leonera", "K03-QU-HQ": "Quilacoya–Hualqui",
    "K02-TL-UN": "Talcamávida–Unihue", "K01-BU-GO": "Buenuraqui–Gomero",
    "L01-BB-LM": "Biobío–Lomas Coloradas", "L02-ES-CW": "Escuadrón–Coronel",
    "L03-LT-IV": "Lota–Chivilingo",
}


def _corr(idstr):
    return re.sub(r"_\d+$", "", idstr or "")


def parse():
    t = etree.parse(str(OTML))
    r = t.getroot()
    leaf = {}
    for n in r.findall(".//node"):
        p = n.find("position")
        xy = (float(p.get("x")), float(p.get("y")))
        for lf in n.findall("leaf"):
            leaf[lf.get("id")] = (xy, _corr(lf.get("id")))

    # rango y por corredor para asignar bandas
    yranges = {}
    for (xy, c) in leaf.values():
        lo, hi = yranges.get(c, (xy[1], xy[1]))
        yranges[c] = (min(lo, xy[1]), max(hi, xy[1]))

    corr_list = [c for c in ORDEN_CORR if c in yranges] + \
                [c for c in yranges if c not in ORDEN_CORR]
    band_h = 1000.0
    offset = {c: i * band_h for i, c in enumerate(corr_list)}

    def place(idstr):
        if idstr not in leaf:
            return None
        (x, y), c = leaf[idstr]
        lo, hi = yranges[c]
        return c, x, (y - lo) + offset[c]

    arcos = []
    for e in r.findall(".//edge"):
        a, b = place(e.get("from")), place(e.get("to"))
        if a and b and a[0] == b[0]:
            arcos.append({"corredor": a[0], "nombre": NOMBRE_CORR.get(a[0], a[0]),
                          "x1": a[1], "y1": a[2], "x2": b[1], "y2": b[2]})
    est = []
    for s in r.findall(".//station"):
        # ubicar estacion por su id (mismo espacio que nodos del corredor)
        c = _corr(s.get("id"))
        p = s.find("position")
        if c in yranges:
            lo, hi = yranges[c]
            est.append({"corredor": c, "label": s.get("label"),
                        "x": float(p.get("x")), "y": (float(p.get("y")) - lo) + offset.get(c, 0)})
    pd.DataFrame(arcos).to_csv(CLEAN / "red_arcos.csv", index=False)
    pd.DataFrame(est).to_csv(CLEAN / "red_estaciones.csv", index=False)
    return pd.DataFrame(arcos), pd.DataFrame(est), corr_list


if __name__ == "__main__":
    arcos, est, corr_list = parse()
    print(f"Arcos: {len(arcos)} | Estaciones: {len(est)} | Corredores: {len(corr_list)}")
    print(arcos.groupby("nombre")["x1"].count().to_string())
