"""Malla del ITINERARIO ACTUAL (Lun-Vie) desde la tabla limpia extraida.

Usa horarios_limpios (tiempos reales por estacion, automotor, equipo vacio) y
arma, por servicio, dos puntos por estacion (llegada y salida) para que la
detencion se vea. Mapea cada estacion a su distancia en el eje (eje_L1/eje_L2).

Salida:
    datos/clean/malla_real.csv
        (linea, tren_id, sentido, unidad, equipo_vacio, estacion, dist_km, hora_min)
"""
import sys
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO / "parsers"))
from config import CLEAN  # noqa: E402
from ejes_distancia import eje_L1, eje_L2  # noqa: E402

DIA = "Lun-Vie"


def generar():
    hl = pd.read_csv(CLEAN / "horarios_limpios.csv")
    pax = hl[(hl.fuente == "pasajeros") & (hl.tipo_dia == DIA)].copy()
    dist = {}
    for linea, eje in [("L2", eje_L2()), ("L1", eje_L1())]:
        for _, r in eje.iterrows():
            dist[(linea, r["estacion"])] = r["dist_km"]
    filas = []
    for (tramo, sent, serv), g in pax.groupby(["tramo", "sentido", "servicio"]):
        g = g.sort_values("orden")
        tid = f"{tramo}-{sent}-{serv}"
        uni = g["unidad"].iloc[0]
        vac = bool(g["equipo_vacio"].iloc[0])
        for _, r in g.iterrows():
            d = dist.get((tramo, r.estacion))
            if d is None:
                continue
            filas.append({"linea": tramo, "tren_id": tid, "sentido": sent, "unidad": uni,
                          "equipo_vacio": vac, "estacion": r.estacion, "dist_km": d,
                          "hora_min": r.llegada_min})
            if r.salida_min != r.llegada_min:
                filas.append({"linea": tramo, "tren_id": tid, "sentido": sent, "unidad": uni,
                              "equipo_vacio": vac, "estacion": r.estacion, "dist_km": d,
                              "hora_min": r.salida_min})
    df = pd.DataFrame(filas)
    df.to_csv(CLEAN / "malla_real.csv", index=False)
    return df


if __name__ == "__main__":
    df = generar()
    for linea in ["L2", "L1"]:
        g = df[df.linea == linea]
        print(f"{linea}: {g['tren_id'].nunique()} trenes "
              f"({g[g.equipo_vacio]['tren_id'].nunique()} vacíos), {len(g)} puntos")
