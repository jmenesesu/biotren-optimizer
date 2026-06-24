"""Cocheras (estacionamientos) de la zona Concepcion.

Fuente: itinerario de pasajeros 2-410, paginas 20-21 ("DISTRIBUCION DE
ESTACIONAMIENTOS ZONA CONCEPCION"). Nomenclatura: <codigo estacion>/<via> (pos),
p. ej. CW/1 (N) = Coronel, via 1, posicion Norte; EZ/2 (A) = El Arenal, via 2,
posicion A. Los prefijos (CW, GU, EZ, ...) son los codigos OpenTrack de la
estacion, lo que permite ubicar cada cochera por km en el modelo.

Salida: datos/clean/cocheras.csv (codigo, estacion, linea, km, capacidad, vias)
"""
import sys
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO / "parsers"))
from config import CLEAN  # noqa: E402
import estaciones_maestro as em  # noqa: E402

# Transcripcion fiel de las paginas 20-21 (codigo estacion -> nombre, linea, vias).
# Nota: en la pagina 20 LM/3 aparece dos veces como "(S)"; se interpreta como las
# dos posiciones de la via 3 (N y S).
COCHERAS = {
    "GU": ("Lagunillas", "L2", ["GU/4 (N)", "GU/4 (C)", "GU/4 (S)"]),
    "CW": ("Coronel", "L2", ["CW/1 (N)", "CW/1 (S)", "CW/2 (N)", "CW/2 (S)"]),
    "LM": ("Lomas Coloradas", "L2", ["LM/3 (N)", "LM/3 (S)"]),
    "CC": ("Concepción", "L2", ["CC/8", "CC/4 (N)", "CC/4 (S)"]),
    "EZ": ("El Arenal", "L1", ["EZ/1 (A)", "EZ/1 (B)", "EZ/1 (C)", "EZ/1 (D)", "EZ/1 (E)",
                               "EZ/2 (A)", "EZ/2 (B)", "EZ/2 (C)"]),
    "ZW": ("La Leonera", "L1", ["ZW/CM"]),
    "HQ": ("Hualqui", "L1", ["HQ/4 (N)", "HQ/4 (S)"]),
    # fuera de la zona Concepcion (no listadas en pags 20-21; capacidad estimada):
    "LJ": ("Laja", "L1", ["LJ/B", "LJ/A"]),
    "OH": ("Omer Huet", "L1", ["Taller OH"]),
}

# Disposicion INICIAL (pernoctacion) por automotor, del grafico de rotaciones
# pagina 16 "LUNES A JUEVES". Codigo = cochera donde amanece cada automotor.
DISPOSICION_INICIAL = {
    "SFE 1": "CW", "SFE 2": "CW", "SFE 8": "CW", "SFE 9": "CW",
    "SFE 3": "CC", "SFE 5": "CC",
    "SFE 4": "LM", "SFE 6": "LM",
    "SFE 7": "GU", "SFE 10": "GU", "SFE 11": "GU",
    "SFE B1": "LJ", "SFE B2": "EZ", "UT 2": "EZ", "SFE B3": "HQ", "UT 1": "OH",
}

# Disposicion de FIN de día (pernoctacion al cierre), grafico de rotaciones pag. 16
# "LUNES A JUEVES (continuacion)". Distribuida (CW=4, GU=3, LM=2, CC=2), no toda
# en Coronel.
DISPOSICION_FINAL = {
    "SFE 1": "CW", "SFE 5": "CW", "SFE 8": "CW", "SFE 10": "CW",
    "SFE 2": "GU", "SFE 3": "GU", "SFE 4": "GU",
    "SFE 7": "LM", "SFE 9": "LM",
    "SFE 6": "CC", "SFE 11": "CC",
    "SFE B1": "EZ",
}
# estacion de fin de servicio -> cochera donde se estaciona (la mayoria coincide;
# los servicios que terminan en Mercado estacionan en el patio de El Arenal).
LAYOVER_A_COCHERA = {
    "Coronel": "CW", "CORONEL": "CW", "Concepción": "CC", "CONCEPCIÓN": "CC",
    "Lagunillas": "GU", "Cristo Redentor": "GU", "Laguna Quiñenco": "GU",
    "Lomas Coloradas": "LM", "LOMAS COLORADAS": "LM",
    "El Arenal": "EZ", "EL ARENAL": "EZ", "Mercado": "EZ", "MERCADO": "EZ",
    "La Leonera": "ZW", "LA LEONERA": "ZW", "Hualqui": "HQ", "HUALQUI": "HQ",
    "Omer Huet": "OH", "OMER HUET": "OH", "Laja": "LJ", "LAJA": "LJ",
}


def construir():
    km_master = em._km_por_codigo()
    rows = []
    for code, (est, linea, vias) in COCHERAS.items():
        km = km_master.get((code, linea))
        rows.append({"codigo": code, "estacion": est, "linea": linea,
                     "km": round(km, 2) if km is not None else None,
                     "capacidad": len(vias), "vias": "; ".join(vias)})
    df = pd.DataFrame(rows).sort_values(["linea", "km"])
    df.to_csv(CLEAN / "cocheras.csv", index=False)
    return df


if __name__ == "__main__":
    df = construir()
    print(f"Cocheras: {len(df)} (capacidad total {int(df.capacidad.sum())} posiciones)")
    print(df.to_string(index=False))
