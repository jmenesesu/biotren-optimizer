"""Eje espacial de cada linea en km MAESTRO de OpenTrack (consistente pax + carga).

Para cada linea, ordena sus estaciones (orden del itinerario) y les asigna el km
maestro (estaciones_maestro.resolver_km); los paraderos sin codigo se interpolan
por posicion entre vecinos conocidos. Asi pasajeros y carga comparten la misma
escala kilometrica y se superponen correctamente.

eje_L1(): Mercado(~85) ... Laja(~1.6)
eje_L2(): Concepcion(~1) ... Coronel(~27.4)
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO / "parsers"))
import estaciones_maestro as em  # noqa: E402

ORDEN_L1 = ["Mercado", "El Arenal", "Hospital Las Higueras", "Los Cóndores", "UTF Santa María",
            "Lorenzo Arenas", "CONCEPCIÓN", "CHIGUAYANTE", "Pedro Medina", "Manquimávida",
            "LA LEONERA", "OMER HUET", "HUALQUI", "QUILACOYA", "San Miguel", "UNIHUE",
            "Valle Chanco", "Los Acacios", "TALCAMÁVIDA", "GOMERO", "BUENURAQUI",
            "SAN ROSENDO", "LAJA"]
ORDEN_L2 = ["CONCEPCIÓN", "Juan Pablo II", "Diagonal Bio Bio", "Alborada", "Costa Mar",
            "El Parque", "LOMAS COLORADAS", "Card. Raúl Silva Henriquez", "Hito Galvarino",
            "Los Canelos", "Huinca", "Cristo Redentor", "Laguna Quiñenco", "CORONEL"]


def _eje(orden, linea):
    km = [em.resolver_km(e, linea) for e in orden]
    idx_known = [i for i, k in enumerate(km) if k is not None]
    # interpolar los None por posicion (orden) entre vecinos conocidos
    for i, k in enumerate(km):
        if k is None:
            prev = max([j for j in idx_known if j < i], default=idx_known[0])
            nxt = min([j for j in idx_known if j > i], default=idx_known[-1])
            if prev == nxt:
                km[i] = km[prev]
            else:
                frac = (i - prev) / (nxt - prev)
                km[i] = km[prev] + frac * (km[nxt] - km[prev])
    return pd.DataFrame({"estacion": orden, "dist_km": [round(x, 3) for x in km]})


def eje_L1():
    return _eje(ORDEN_L1, "L1")


def eje_L2():
    return _eje(ORDEN_L2, "L2")


if __name__ == "__main__":
    print("=== eje L1 (km maestro) ===")
    print(eje_L1().to_string(index=False))
    print("\n=== eje L2 (km maestro) ===")
    print(eje_L2().to_string(index=False))
