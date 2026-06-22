"""Tabla maestra de estaciones con km de OpenTrack + alias de nombres.

Reconcilia los DISTINTOS nombres (pasajeros, carga, oficial) de la MISMA red
mediante un diccionario de alias -> codigo, y entrega el km por linea:
  - km_l1: cadena longitudinal Laja(0)..Mercado(~85) (corredores K01..K06).
  - km_l2: cadena costera Concepcion(~1)..Coronel(~27) (corredores L01..L03).

API:
  resolver_km(nombre, linea) -> km (float) o None
  km_eje(linea) -> dict {codigo: km} de las estaciones de esa linea
"""
import re
import sys
import unicodedata
from pathlib import Path
import pandas as pd
from lxml import etree

sys.path.append(str(Path(__file__).resolve().parent))
from config import INFRA_DIR, STA_DIR, CLEAN  # noqa: E402

GRUPO_DOC = {"K01-BU-GO": "L1", "K02-TL-UN": "L1", "K03-QU-HQ": "L1",
             "K-04-OH-ZW-CV 1": "L1", "K05-CC": "L1", "K-06-EZ-TH 1": "L1",
             "L01-BB-LM": "L2", "L02-ES-CW": "L2", "L03-LT-IV": "L2"}

# alias (nombre normalizado) -> codigo. Cubre nombres de pasajeros y carga.
ALIAS = {
    # L1 longitudinal
    "MERCADO": "TH", "TALCAHUANO": "TH", "EL ARENAL": "EZ", "ARENAL": "EZ",
    "HOSPITAL LAS HIGUERAS": "CCEZ4", "HIGUERAS": "CCEZ4", "HOSP HIGUERAS": "CCEZ4",
    "LOS CONDORES": "CCEZ3", "UTF SANTA MARIA": "CCEZ2", "UTFSM": "CCEZ2",
    "LORENZO ARENAS": "CCEZ1", "LZO ARENAS": "CCEZ1",
    "CONCEPCION": "CC", "CHIGUAYANTE": "CV", "LA LEONERA": "ZW", "OMER HUET": "OH",
    "HUALQUI": "HQ", "QUILACOYA": "QU", "UNIHUE": "UN", "TALCAMAVIDA": "TL",
    "GOMERO": "GO", "BUENURAQUI": "BU", "SAN ROSENDO": "SR", "LAJA": "LJ",
    # L2 costera
    "BIOBIO": "BB", "JUAN PABLO II": "BBJ", "JPII": "BBJ", "DIAGONAL BIO BIO": "BBD",
    "DIAGONAL BIOBIO": "BBD", "ALBORADA": "SU", "BOCA SUR": "SU",
    "LOMAS COLORADAS": "LM", "ESCUADRON": "ES", "LAGUNILLAS": "GU",
    "CRISTO REDENTOR": "GU", "CORONEL": "CW", "LOTA": "LT",
}
# km sinteticos / extra (no tagueados en infra)
KM_EXTRA = {("SR", "L1"): 4.0, ("LJ", "L1"): 1.6, ("CC", "L2"): 1.0}


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().upper()
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


_KM = None


def _km_por_codigo():
    """{(codigo, linea): km} desde infra + extras."""
    global _KM
    if _KM is not None:
        return _KM
    e = pd.read_csv(CLEAN / "infra_edges.csv")
    rows = []
    for _, r in e.iterrows():
        g = GRUPO_DOC.get(r.document)
        if not g:
            continue
        for c, k in [(r.v1_stat_id, r.v1_km), (r.v2_stat_id, r.v2_km)]:
            if pd.notna(c) and pd.notna(k):
                rows.append((str(c), g, float(k)))
    km = pd.DataFrame(rows, columns=["code", "linea", "km"]).groupby(["code", "linea"])["km"].mean()
    d = km.to_dict()
    d.update(KM_EXTRA)
    _KM = d
    return d


def resolver_km(nombre, linea):
    code = ALIAS.get(_norm(nombre))
    if not code:
        return None
    return _km_por_codigo().get((code, linea))


def construir():
    # tabla informativa codigo->nombre->km
    t = etree.parse(str(STA_DIR / "Export Stations (railML-Format) - Version 2.2.railml"))
    ns = {"r": "http://www.railml.org/schemas/2013"}
    nombre = {o.get("abbrevation") or o.get("code"): o.get("name") for o in t.findall(".//r:ocp", ns)}
    d = _km_por_codigo()
    rows = [{"code": c, "linea": l, "km": k, "nombre": nombre.get(c, "")} for (c, l), k in d.items()]
    df = pd.DataFrame(rows).sort_values(["linea", "km"])
    df.to_csv(CLEAN / "estaciones_maestro.csv", index=False)
    return df


if __name__ == "__main__":
    df = construir()
    print(f"Maestro: {len(df)} (codigo,linea)")
    print("\nPruebas resolver_km (nombre, linea) -> km:")
    for nm, ln in [("Concepción", "L2"), ("Biobío", "L2"), ("Boca Sur", "L2"),
                   ("Escuadrón", "L2"), ("Lagunillas", "L2"), ("Coronel", "L2"),
                   ("Hualqui", "L1"), ("Buenuraqui", "L1"), ("Laja", "L1"), ("Mercado", "L1")]:
        print(f"  {nm:14} {ln} -> {resolver_km(nm, ln)}")


MAIN_SIG = {"Main Signal", "Main Signal 2 Aspect", "Main/Distant Sig. 3 Asp.",
            "Main/Distant Signal"}


def senales_principales_km(linea):
    """km (cadena maestra) de las senales PRINCIPALES de la linea, desde Metrolinx.
    Una senal principal delimita un canton (block)."""
    e = pd.read_csv(CLEAN / "infra_edges.csv")
    kms = []
    for _, r in e.iterrows():
        if GRUPO_DOC.get(r["document"]) != linea:
            continue
        for sig, km in [(r.get("v1_sig"), r.get("v1_km")), (r.get("v2_sig"), r.get("v2_km"))]:
            if pd.notna(sig) and pd.notna(km) and sig in MAIN_SIG:
                kms.append(round(float(km), 2))
    return sorted(set(kms))
