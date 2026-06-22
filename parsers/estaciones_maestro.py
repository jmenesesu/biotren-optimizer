"""Tabla maestra de estaciones: codigo -> nombre -> km, desde OpenTrack.

Unifica los nombres de pasajeros y de carga (que difieren) usando los km de la
infraestructura de OpenTrack. Define dos cadenas de kilometraje:
  - grupo 'L1': corredor longitudinal Laja-Mercado (corredores K01..K06), km continuo.
  - grupo 'L2': corredor costero Concepcion-Coronel-Lota (L01..L03).

Provee resolver(nombre) -> (codigo, grupo, km) para mapear cualquier nombre
(pasajeros o carga) a su posicion en la red.

Salida:
    datos/clean/estaciones_maestro.csv
"""
import re
import sys
import unicodedata
from pathlib import Path
import pandas as pd
from lxml import etree

sys.path.append(str(Path(__file__).resolve().parent))
from config import INFRA_DIR, STA_DIR, CLEAN  # noqa: E402

GRUPO_DOC = {  # corredor -> grupo de cadena de km
    "K01-BU-GO": "L1", "K02-TL-UN": "L1", "K03-QU-HQ": "L1",
    "K-04-OH-ZW-CV 1": "L1", "K05-CC": "L1", "K-06-EZ-TH 1": "L1",
    "L01-BB-LM": "L2", "L02-ES-CW": "L2", "L03-LT-IV": "L2",
}
# km aproximado para estaciones del extremo Laja no tagueadas en infra (grupo L1)
KM_EXTRA_L1 = {"SAN ROSENDO": 4.0, "LAJA": 1.6}


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().upper()
    s = re.sub(r"\(.*?\)", "", s)            # quitar parentesis
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def construir():
    # 1) km por codigo y corredor (infra)
    e = pd.read_csv(CLEAN / "infra_edges.csv")
    rows = []
    for _, r in e.iterrows():
        for c, k in [(r.v1_stat_id, r.v1_km), (r.v2_stat_id, r.v2_km)]:
            if pd.notna(c) and pd.notna(k):
                rows.append((r.document, str(c), float(k)))
    km = pd.DataFrame(rows, columns=["doc", "code", "km"]).groupby(["doc", "code"])["km"].mean().reset_index()
    km["grupo"] = km["doc"].map(GRUPO_DOC)
    km = km.dropna(subset=["grupo"])
    # un km por codigo (si aparece en varios corredores del mismo grupo, promedio)
    kmc = km.groupby(["code", "grupo"])["km"].mean().reset_index()

    # 2) codigo -> nombre (railML)
    t = etree.parse(str(STA_DIR / "Export Stations (railML-Format) - Version 2.2.railml"))
    ns = {"r": "http://www.railml.org/schemas/2013"}
    nombre = {o.get("abbrevation") or o.get("code"): o.get("name") for o in t.findall(".//r:ocp", ns)}

    kmc["nombre"] = kmc["code"].map(nombre)
    kmc["nombre_norm"] = kmc["nombre"].map(_norm)
    kmc.to_csv(CLEAN / "estaciones_maestro.csv", index=False)
    return kmc


_RES = None


def _resolver_tabla():
    global _RES
    if _RES is None:
        f = CLEAN / "estaciones_maestro.csv"
        m = pd.read_csv(f) if f.exists() else construir()
        _RES = m
    return _RES


def resolver(nombre, grupo=None):
    """nombre (pasajeros o carga) -> (codigo, grupo, km) o None."""
    m = _resolver_tabla()
    n = _norm(nombre)
    cand = m[m["nombre_norm"] == n]
    if grupo is not None:
        cand = cand[cand["grupo"] == grupo]
    if len(cand):
        r = cand.iloc[0]
        return (r["code"], r["grupo"], float(r["km"]))
    # extras del extremo Laja
    if n in KM_EXTRA_L1 and (grupo in (None, "L1")):
        return (n[:3], "L1", KM_EXTRA_L1[n])
    return None


if __name__ == "__main__":
    m = construir()
    print(f"Estaciones maestras: {len(m)} | por grupo: {m.groupby('grupo')['code'].count().to_dict()}")
    print("\nPruebas de resolver (nombres de carga y pasajeros):")
    for nm in ["Hualqui", "Quilacoya", "Buenuraqui", "Gomero", "Concepción", "El Arenal",
               "Biobío", "Boca Sur", "Lomas Coloradas", "Escuadrón", "Lagunillas", "Coronel",
               "Laja", "San Rosendo", "Chiguayante", "La Leonera"]:
        print(f"  {nm:18} -> {resolver(nm)}")
