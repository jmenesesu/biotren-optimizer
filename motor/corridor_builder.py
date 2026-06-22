"""Constructor de perfil real de via por tramo inter-estacion.

A partir de los arcos limpios (infra_edges.csv) construye, para una linea y
sentido, el perfil continuo de velocidad limite y gradiente en funcion del
kilometraje, deduplica la doble via y ubica las estaciones por kilometraje
(anclas tagueadas + interpolacion por tiempo de itinerario para los paraderos
no tagueados). Entrega, por tramo inter-estacion, la lista de SubTramo real
para alimentar el motor de tiempos.

Reemplaza el perfil uniforme de la validacion preliminar por el perfil real.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1] / "parsers"))
from config import CLEAN  # noqa: E402
from running_time import SubTramo  # noqa: E402

# Corredores que componen cada linea Biotren, en orden de kilometraje creciente
CORREDORES_LINEA = {
    "L2": ["L01-BB-LM", "L02-ES-CW"],   # Concepcion -> Coronel
}

# Mapeo estacion de itinerario -> codigo de estacion tagueado en la infra
# (solo las estaciones con ancla kilometrica fiable). Las demas se interpolan.
ANCLAS_L2 = {
    "CONCEPCIÓN": 0.0,            # origen de la linea
    "Juan Pablo II": "BBJ",
    "Diagonal Bio Bio": "BBD",
    "Alborada": "SU",            # Boca Sur (Alborada)
    "LOMAS COLORADAS": "LM",
    "CORONEL": 28.4,             # distancia oficial Coronel-Concepcion
    # "Laguna Quinenco" NO se ancla a GU: GU (Desvio Lagunillas) es un desvio de
    # carga, no el paradero. Se interpola por tiempo entre LM y Coronel.
}


def km_ancla(edges_linea: pd.DataFrame, code: str) -> float:
    sub = edges_linea[(edges_linea.v1_stat_id == code) | (edges_linea.v2_stat_id == code)]
    kk = pd.concat([sub.v1_km, sub.v2_km]).dropna()
    return float(kk.mean())


def perfil_continuo(edges_linea: pd.DataFrame, bin_km: float = 0.1) -> pd.DataFrame:
    """Perfil (km -> vmax, gradiente) deduplicando doble via por binning."""
    e = edges_linea.copy()
    e["km_mid"] = (e.v1_km + e.v2_km) / 2
    e = e.dropna(subset=["km_mid"])
    e["vmax_uso"] = e["vmax_kmh"].replace(200, np.nan)  # 200 = sin limite especifico
    e["bin"] = (e["km_mid"] / bin_km).round().astype(int)
    agg = e.groupby("bin").agg(
        km=("km_mid", "mean"),
        vmax_kmh=("vmax_uso", "median"),
        gradiente_permil=("gradient_permil", "mean"),
        largo_m=("edge_length_m", "mean"),
    ).reset_index(drop=True).sort_values("km")
    agg["vmax_kmh"] = agg["vmax_kmh"].ffill().bfill()
    return agg


def ubicar_estaciones(itin_linea: pd.DataFrame, edges_linea: pd.DataFrame,
                      anclas: dict) -> pd.DataFrame:
    """Estaciones en orden con su km (anclas + interpolacion por tiempo)."""
    estaciones = list(itin_linea["estacion"])
    t_viaje = list(itin_linea["t_viaje_s"])
    km = [None] * len(estaciones)
    tcum = np.cumsum(t_viaje)

    for i, est in enumerate(estaciones):
        if est in anclas:
            v = anclas[est]
            km[i] = float(v) if isinstance(v, (int, float)) else km_ancla(edges_linea, v)

    idx_known = [i for i, v in enumerate(km) if v is not None]
    for i in range(len(km)):
        if km[i] is None:
            prev = max([j for j in idx_known if j < i], default=idx_known[0])
            nxt = min([j for j in idx_known if j > i], default=idx_known[-1])
            if prev == nxt:
                km[i] = km[prev]
            else:
                frac = (tcum[i] - tcum[prev]) / (tcum[nxt] - tcum[prev])
                km[i] = km[prev] + frac * (km[nxt] - km[prev])
    out = itin_linea.copy()
    out["km"] = km
    return out


def subtramos_entre(perfil: pd.DataFrame, km_ini: float, km_fin: float) -> list:
    """Lista de SubTramo del perfil real entre dos kilometrajes."""
    lo, hi = min(km_ini, km_fin), max(km_ini, km_fin)
    seg = perfil[(perfil.km >= lo) & (perfil.km <= hi)].sort_values("km")
    if len(seg) < 2:
        v = perfil.iloc[(perfil.km - (lo + hi) / 2).abs().argmin()]
        return [SubTramo((hi - lo) * 1000.0, float(v.vmax_kmh), float(v.gradiente_permil))]
    subs = []
    kms = seg.km.to_numpy()
    for j in range(1, len(kms)):
        largo = (kms[j] - kms[j - 1]) * 1000.0
        if largo <= 0:
            continue
        fila = seg.iloc[j]
        subs.append(SubTramo(largo, float(fila.vmax_kmh), float(fila.gradiente_permil)))
    return subs


def construir_linea(linea: str = "L2", sentido: str = "CC->CW"):
    edges = pd.read_csv(CLEAN / "infra_edges.csv")
    itin = pd.read_csv(CLEAN / "itinerario_tiempos.csv")
    edges_linea = edges[edges.document.isin(CORREDORES_LINEA[linea])]
    perfil = perfil_continuo(edges_linea)
    itin_l = itin[(itin.tramo == linea) & (itin.sentido == sentido)].reset_index(drop=True)
    estaciones = ubicar_estaciones(itin_l, edges_linea, ANCLAS_L2)
    return perfil, estaciones


if __name__ == "__main__":
    perfil, est = construir_linea()
    print("Perfil continuo L2: %d puntos, km %.2f a %.2f" %
          (len(perfil), perfil.km.min(), perfil.km.max()))
    print("vmax mediana %.0f km/h | gradiente [%.1f, %.1f] permil" %
          (perfil.vmax_kmh.median(), perfil.gradiente_permil.min(), perfil.gradiente_permil.max()))
    print("Ubicacion de estaciones (km):")
    print(est[["estacion", "km", "t_viaje_s"]].to_string(index=False))
