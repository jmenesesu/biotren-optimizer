"""Construye el eje espacial (distancia acumulada) de cada linea para el Marey.

L2: km reales del corridor_builder (Concepcion=0 .. Coronel=28.4).
L1: orden Mercado -> Concepcion -> Hualqui -> Laja, con distancia acumulada desde
    Mercado, usando:
      - haversine entre coordenadas reales (Mercado..Hualqui, del KML),
      - km de la infraestructura para el tramo Hualqui..Buenuraqui (K-corredores),
      - extension a San Rosendo/Laja por distancias parciales conocidas,
      - interpolacion por tiempo de itinerario para paraderos sin dato.

Devuelve, por linea, un DataFrame ordenado [estacion, dist_km] (creciente desde
el origen). La orientacion del eje (quien va arriba) se decide al graficar.
"""
import sys
from math import radians, sin, cos, asin, sqrt
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO / "parsers"))
sys.path.append(str(REPO / "motor"))
from config import CLEAN  # noqa: E402
from corridor_builder import construir_linea  # noqa: E402

# Orden L1 de Mercado a Laja (nombres del itinerario / red)
ORDEN_L1 = ["Mercado", "El Arenal", "Hospital Las Higueras", "Los Cóndores",
            "UTF Santa María", "Lorenzo Arenas", "CONCEPCIÓN", "CHIGUAYANTE",
            "Pedro Medina", "Manquimávida", "LA LEONERA", "OMER HUET", "HUALQUI",
            "QUILACOYA", "San Miguel", "UNIHUE", "Valle Chanco", "Los Acacios",
            "TALCAMÁVIDA", "GOMERO", "BUENURAQUI", "SAN ROSENDO", "LAJA"]

# km de infraestructura (chainage Laja) por estacion taggeada
KM_INFRA_L1 = {"HUALQUI": 47.0, "QUILACOYA": 36.7, "UNIHUE": 29.5,
               "TALCAMÁVIDA": 22.9, "GOMERO": 15.4, "BUENURAQUI": 8.4,
               "SAN ROSENDO": 5.0, "LAJA": 2.4}  # San Rosendo/Laja aprox (parciales)

# Nombre itinerario -> nombre en estaciones_geo (para coordenadas)
GEO_NOMBRE = {
    "Mercado": "Mercado", "El Arenal": "El Arenal", "Hospital Las Higueras": "Higueras",
    "Los Cóndores": "Los Cóndores", "UTF Santa María": "UTF Santa María",
    "Lorenzo Arenas": "Lzo. Arenas", "CONCEPCIÓN": "Concepción",
    "CHIGUAYANTE": "Chiguayante", "Pedro Medina": "Pedro Medina",
    "Manquimávida": "Manquimávida", "LA LEONERA": "La Leonera", "HUALQUI": "Hualqui",
}


def _haversine(a, b):
    lat1, lon1, lat2, lon2 = map(radians, [a[0], a[1], b[0], b[1]])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * 6371.0 * asin(sqrt(h))


def eje_L2():
    perfil, est = construir_linea("L2", "CC->CW")
    filas = [("CONCEPCIÓN", 0.0)] + [(r["estacion"], float(r["km"])) for _, r in est.iterrows()]
    return pd.DataFrame(filas, columns=["estacion", "dist_km"])


def eje_L1():
    geo = pd.read_csv(CLEAN / "estaciones_geo.csv")
    coords = {r["estacion"]: (r["lat"], r["lon"]) for _, r in geo.iterrows()}
    it = pd.read_csv(CLEAN / "itinerario_tiempos.csv")
    l1 = it[(it.tramo == "L1") & (it.sentido == "LJ->TH")]
    tviaje = dict(zip(l1["estacion"], l1["t_viaje_s"]))  # t de viaje hacia esa estacion

    # 1) distancia acumulada desde Mercado por haversine (Mercado..Hualqui)
    dist = {}
    acc = 0.0
    prev_geo = None
    for est in ORDEN_L1:
        gname = GEO_NOMBRE.get(est)
        if gname and gname in coords:
            if prev_geo is not None:
                acc += _haversine(prev_geo, coords[gname])
            dist[est] = acc
            prev_geo = coords[gname]
    d_hualqui = dist["HUALQUI"]

    # 2) tramo Hualqui..Laja con km de infraestructura (distancia desde Hualqui)
    for est, km in KM_INFRA_L1.items():
        if est == "HUALQUI":
            continue
        dist[est] = d_hualqui + (KM_INFRA_L1["HUALQUI"] - km)

    # 3) paraderos sin dato (San Miguel, Valle Chanco, Los Acacios, OMER HUET):
    #    interpolar por tiempo de itinerario entre vecinos conocidos
    for i, est in enumerate(ORDEN_L1):
        if est in dist:
            continue
        # vecino anterior y siguiente con distancia
        prev = next((ORDEN_L1[j] for j in range(i - 1, -1, -1) if ORDEN_L1[j] in dist), None)
        nxt = next((ORDEN_L1[j] for j in range(i + 1, len(ORDEN_L1)) if ORDEN_L1[j] in dist), None)
        if prev and nxt:
            # peso por tiempo acumulado del itinerario entre prev..nxt
            seg = ORDEN_L1[ORDEN_L1.index(prev):ORDEN_L1.index(nxt) + 1]
            tt = [tviaje.get(s, 60) for s in seg[1:]]
            tcum, total = [], sum(tt)
            run = 0
            for s, t in zip(seg[1:], tt):
                run += t
                tcum.append(run)
            frac = (tcum[seg[1:].index(est)] / total) if total else 0.5
            dist[est] = dist[prev] + frac * (dist[nxt] - dist[prev])
        elif prev:
            dist[est] = dist[prev]
    filas = [(est, round(dist[est], 3)) for est in ORDEN_L1 if est in dist]
    return pd.DataFrame(filas, columns=["estacion", "dist_km"])


if __name__ == "__main__":
    print("=== Eje L2 ===")
    print(eje_L2().to_string(index=False))
    print("\n=== Eje L1 (Mercado=0 -> Laja) ===")
    d = eje_L1()
    print(d.to_string(index=False))
    print("monotona creciente:", d["dist_km"].is_monotonic_increasing)
