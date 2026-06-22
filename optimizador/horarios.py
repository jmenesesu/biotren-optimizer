"""Base comun de horarios: por servicio y estacion, hora de LLEGADA y SALIDA.

Reconstruye el horario estacion a estacion a partir de la hora de salida real de
cada servicio (salidas_reales) y de los tiempos de viaje y detencion del
itinerario. Es el formato limpio (legible) que alimenta tanto las tablas de
horarios como los diagramas de Marey (con detenciones).

Salida:
    datos/clean/horarios_nominal.csv
        (linea, sentido, servicio, unidad, orden, estacion, dist_km,
         llegada_min, salida_min)
"""
import sys
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO / "parsers"))
from config import CLEAN  # noqa: E402
from ejes_distancia import eje_L1, eje_L2  # noqa: E402

CRECE = {"L2": "CC->CW", "L1": "TH->LJ"}   # sentido de distancia creciente


def _eje(linea):
    return eje_L2() if linea == "L2" else eje_L1()


def horario_servicio(linea, sentido, salida_min, itin):
    """Lista [estacion, dist_km, llegada_min, salida_min] del servicio."""
    eje = _eje(linea)
    estaciones = list(eje["estacion"]); distkm = dict(zip(eje["estacion"], eje["dist_km"]))
    orden = estaciones if sentido == CRECE[linea] else list(reversed(estaciones))
    sub = itin[(itin.tramo == linea) & (itin.sentido == sentido)]
    tviaje = dict(zip(sub["estacion"], sub["t_viaje_s"].fillna(0) / 60.0))
    deten = dict(zip(sub["estacion"], sub["detencion_s"].fillna(0) / 60.0))
    filas = []
    t = salida_min
    for i, est in enumerate(orden):
        if i == 0:
            lleg = sal = salida_min            # origen
        else:
            lleg = t + tviaje.get(est, 1.0)
            sal = lleg + (deten.get(est, 0.0) if i < len(orden) - 1 else 0.0)
        filas.append({"estacion": est, "dist_km": round(distkm[est], 3),
                      "llegada_min": round(lleg, 2), "salida_min": round(sal, 2)})
        t = sal
    return filas


def construir():
    sal = pd.read_csv(CLEAN / "salidas_reales.csv")
    itin = pd.read_csv(CLEAN / "itinerario_tiempos.csv")
    filas = []
    for _, r in sal.iterrows():
        h = horario_servicio(r.linea, r.sentido, r.salida_min, itin)
        for orden, f in enumerate(h):
            filas.append({"linea": r.linea, "sentido": r.sentido, "servicio": r.servicio,
                          "unidad": getattr(r, "unidad", ""), "orden": orden, **f})
    df = pd.DataFrame(filas)
    df.to_csv(CLEAN / "horarios_nominal.csv", index=False)
    return df


def _mmss(x):
    if pd.isna(x):
        return ""
    h = int(x // 60) % 24; m = int(round(x % 60))
    if m == 60:
        h = (h + 1) % 24; m = 0
    return f"{h:02d}:{m:02d}"


def tabla(linea, sentido):
    """Tabla legible: filas = estaciones (en orden), columnas = servicio, valor = salida HH:MM."""
    df = pd.read_csv(CLEAN / "horarios_nominal.csv")
    d = df[(df.linea == linea) & (df.sentido == sentido)].copy()
    if d.empty:
        return pd.DataFrame()
    d["hora"] = d["salida_min"].map(_mmss)
    # orden de estaciones
    est_order = d.sort_values("orden")["estacion"].drop_duplicates().tolist()
    # encabezado de columna: servicio (unidad)
    d["col"] = d.apply(lambda r: f"{r.servicio}", axis=1)
    piv = d.pivot_table(index="estacion", columns="col", values="hora", aggfunc="first")
    piv = piv.reindex(est_order)
    return piv.reset_index()


if __name__ == "__main__":
    df = construir()
    print(f"Filas horario: {len(df)} | servicios: {df.groupby(['linea','sentido'])['servicio'].nunique().to_dict()}")
    print("\nEjemplo tabla L2 CC->CW (primeras estaciones y 6 servicios):")
    t = tabla("L2", "CC->CW")
    print(t.iloc[:6, :7].to_string(index=False))
