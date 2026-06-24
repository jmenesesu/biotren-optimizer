"""Enlaces (escapes/comunicaciones) DIRIGIDOS, leídos de la Tira Larga (planos de
circuitos de vía de EFE Sur). Cada escape conecta dos vías y solo es tomable "de
punta" (facing) para un sentido de marcha; en el sentido contrario, ese mismo
escape es "de talón" y no sirve para ese cambio.

Modelo: cada escape se describe por su km y los MOVIMIENTOS que habilita, cada uno
como (via_origen, via_destino, sentido) donde sentido = sentido de marcha para el
que el escape abre. 'der' = vía derecha (km creciente, →); 'izq' = vía izquierda
(km decreciente, ←).

Fuente: "Tira larga EA CC-CW imp.pdf" (L2). La orientación de cada escape se tomó
de la geometría del plano; conviene validar en el plano a alta resolución.
Por ahora L2; L1 (HQ-TH) queda pendiente de la misma extracción.

Salida: datos/clean/enlaces_dirigidos.csv
"""
import sys
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO / "parsers"))
from config import CLEAN  # noqa: E402

# Escapes de L2 leídos de la tira larga. km = km maestro aprox. del grupo de agujas.
# moves: lista de (via_origen, via_destino, sentido_marcha_que_lo_puede_tomar).
#   der = Principal poniente (km creciente, →); izq = Principal oriente (km decrec., ←)
ESCAPES_L2 = [
    {"estacion": "Concepción/Chepe", "km": 3.10, "agujas": "Ag.1 (PK 2/58)",
     "tipo": "comunicación", "moves": [("der", "izq", "der"), ("izq", "der", "izq")]},
    {"estacion": "Boca Sur", "km": 7.44, "agujas": "E.A. PK 4/21-4/22",
     "tipo": "comunicación", "moves": [("der", "izq", "der"), ("izq", "der", "izq")]},
    {"estacion": "Lomas Coloradas", "km": 11.03, "agujas": "E.A. PK 9/5-9/6",
     "tipo": "comunicación", "moves": [("der", "izq", "der"), ("izq", "der", "izq")]},
    {"estacion": "Escuadrón", "km": 19.40, "agujas": "Ag.2/Ag.4",
     "tipo": "comunicación", "moves": [("der", "izq", "der"), ("izq", "der", "izq")]},
    {"estacion": "Coronel", "km": 27.36, "agujas": "Ag.9/Ag.11",
     "tipo": "terminal", "moves": [("der", "izq", "der"), ("izq", "der", "izq")]},
]


def construir():
    filas = []
    for e in ESCAPES_L2:
        for (vo, vd, se) in e["moves"]:
            filas.append({"linea": "L2", "estacion": e["estacion"], "km": e["km"],
                          "agujas": e["agujas"], "tipo": e["tipo"],
                          "via_origen": vo, "via_destino": vd, "sentido": se})
    df = pd.DataFrame(filas)
    df.to_csv(CLEAN / "enlaces_dirigidos.csv", index=False)
    return df


if __name__ == "__main__":
    df = construir()
    print(f"Enlaces dirigidos (L2): {df['estacion'].nunique()} escapes, {len(df)} movimientos")
    print(df.to_string(index=False))
