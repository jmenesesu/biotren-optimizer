"""Parser de coordenadas georreferenciadas de las estaciones Biotren (KML).

Lee 'Estaciones Biotren.kml' (carpeta de insumos) y produce un CSV con la
latitud/longitud reales de cada estacion, su linea y su orden a lo largo de la
linea, para el mapa y para dibujar la traza.

Uso:
    python parsers/parse_geo.py
Salida:
    datos/clean/estaciones_geo.csv  (estacion, nombre_kml, linea, orden, lat, lon, fuente)
"""
import sys
from pathlib import Path
import pandas as pd
from lxml import etree

sys.path.append(str(Path(__file__).resolve().parent))
from config import INSUMOS, CLEAN  # noqa: E402

KML = INSUMOS / "Estaciones Biotren.kml"

# Mapeo nombre KML -> nombre de red (igual al usado en la matriz OD / la red)
NOMBRE_RED = {
    "Mercado": "Mercado", "El Arenal": "El Arenal", "Hosp. Higueras": "Higueras",
    "Los Cóndores": "Los Cóndores", "U.T.F.S.M.": "UTF Santa María",
    "Lorenzo Arenas": "Lzo. Arenas", "Concepción": "Concepción",
    "Chiguayante": "Chiguayante", "Pedro Medina": "Pedro Medina",
    "Manquimávida": "Manquimávida", "La Leonera": "La Leonera", "Hualqui": "Hualqui",
    "J.P.II": "Juan Pablo II", "Diagonal Biobío": "Diagonal Bio Bio",
    "Alborada": "Alborada", "Costa Mar": "Costa Mar", "El Parque": "El Parque",
    "Lomas Coloradas": "Lomas Coloradas", "C.R.S.H": "Cdal. Raúl Silva Henríquez",
    "Hito Galvarino": "Hito Galvarino", "Los Canelos": "Los Canelos",
    "Huinca": "Huinca", "Cristo Redentor": "Cristo Redentor",
    "Laguna Quiñenco": "Laguna Quiñenco", "Intermodal Coronel": "Coronel",
}

# Secuencia de cada linea (orden de la traza). Concepcion aparece en ambas (nodo).
SEC_L1 = ["Mercado", "El Arenal", "Hosp. Higueras", "Los Cóndores", "U.T.F.S.M.",
          "Lorenzo Arenas", "Concepción", "Chiguayante", "Pedro Medina",
          "Manquimávida", "La Leonera", "Hualqui"]
SEC_L2 = ["Concepción", "J.P.II", "Diagonal Biobío", "Alborada", "Costa Mar",
          "El Parque", "Lomas Coloradas", "C.R.S.H", "Hito Galvarino",
          "Los Canelos", "Huinca", "Cristo Redentor", "Laguna Quiñenco",
          "Intermodal Coronel"]


def parse():
    t = etree.parse(str(KML))
    for el in t.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    coords = {}
    for p in t.findall(".//Placemark"):
        name = (p.findtext("name") or "").strip()
        c = (p.findtext(".//coordinates") or "").strip()
        if not name or not c:
            continue
        lon, lat = c.split(",")[:2]
        coords[name] = (float(lat), float(lon))

    filas = []
    for linea, seq in [("L1", SEC_L1), ("L2", SEC_L2)]:
        for orden, kml_name in enumerate(seq):
            if kml_name not in coords:
                continue
            lat, lon = coords[kml_name]
            filas.append({
                "estacion": NOMBRE_RED.get(kml_name, kml_name),
                "nombre_kml": kml_name, "linea": linea, "orden": orden,
                "lat": lat, "lon": lon, "fuente": "GIS EFE Sur (KML)",
            })
    df = pd.DataFrame(filas)
    df.to_csv(CLEAN / "estaciones_geo.csv", index=False)
    return df


if __name__ == "__main__":
    df = parse()
    print(f"Estaciones georreferenciadas: {len(df)} (L1={sum(df.linea=='L1')}, L2={sum(df.linea=='L2')})")
    print(df[["estacion", "linea", "orden", "lat", "lon"]].to_string(index=False))
    print(f"\nGuardado: {CLEAN/'estaciones_geo.csv'}")
