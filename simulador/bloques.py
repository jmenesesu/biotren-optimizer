"""Modelo de bloques (cantones) de via para la simulacion fixed-block.

Un canton es un tramo de via entre dos limites (estaciones y bordes de via unica).
  - tipo 'single': via unica -> capacidad 1 tren, compartido por AMBOS sentidos.
  - tipo 'double': doble via -> capacidad 1 tren POR SENTIDO.

Los limites se toman de las estaciones (eje espacial) mas los bordes de los
tramos de via unica. Es un fixed-block a nivel de estacion/seccion (no por cada
senal), suficiente para validar ocupacion y cruzamientos.

Salida:
    datos/clean/bloques.csv  (linea, block_id, dist_lo, dist_hi, tipo, nombre)
"""
import sys
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO / "parsers"))
sys.path.append(str(REPO / "optimizador"))
from config import CLEAN  # noqa: E402
from ejes_distancia import eje_L1, eje_L2  # noqa: E402
from via_unica import VIA_UNICA  # noqa: E402


def _bloques_linea(linea, eje):
    est = eje.sort_values("dist_km").reset_index(drop=True)
    # limites: estaciones + bordes de via unica
    limites = set(round(d, 3) for d in est["dist_km"])
    for nombre, lo, hi, bloquea in VIA_UNICA.get(linea, []):
        limites.add(round(lo, 3)); limites.add(round(hi, 3))
    limites = sorted(limites)
    # nombre de cada limite (estacion mas cercana)
    nombre_de = {round(r.dist_km, 3): r.estacion for _, r in est.iterrows()}
    filas = []
    for i in range(len(limites) - 1):
        lo, hi = limites[i], limites[i + 1]
        mid = (lo + hi) / 2
        tipo = "double"
        for _, vlo, vhi, bloquea in VIA_UNICA.get(linea, []):
            if vlo - 1e-6 <= mid <= vhi + 1e-6 and bloquea:
                tipo = "single"
        a = nombre_de.get(lo, f"km{lo:.1f}")
        b = nombre_de.get(hi, f"km{hi:.1f}")
        filas.append({"linea": linea, "block_id": f"{linea}-B{i}",
                      "dist_lo": lo, "dist_hi": hi, "tipo": tipo, "nombre": f"{a} → {b}"})
    return filas


def construir():
    filas = _bloques_linea("L2", eje_L2()) + _bloques_linea("L1", eje_L1())
    df = pd.DataFrame(filas)
    df.to_csv(CLEAN / "bloques.csv", index=False)
    return df


if __name__ == "__main__":
    df = construir()
    for linea in ["L2", "L1"]:
        g = df[df.linea == linea]
        print(f"{linea}: {len(g)} cantones ({(g.tipo=='single').sum()} via unica)")
    print("\nCantones L2:")
    print(df[df.linea == "L2"][["block_id", "dist_lo", "dist_hi", "tipo", "nombre"]].to_string(index=False))
