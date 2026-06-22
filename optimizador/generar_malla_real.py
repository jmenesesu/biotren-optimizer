"""Malla del ITINERARIO ACTUAL (as-is) con detenciones, para el Marey.

Lee horarios_nominal (llegada/salida por estacion) y emite, por servicio, dos
puntos por estacion (llegada y salida) de modo que la detencion se vea como un
segmento horizontal en el diagrama.

Salida:
    datos/clean/malla_real.csv  (linea, tren_id, sentido, unidad, estacion, dist_km, hora_min)
"""
import sys
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO / "parsers"))
from config import CLEAN  # noqa: E402
import horarios  # noqa: E402  (asegura que exista la base)


def generar():
    if not (CLEAN / "horarios_nominal.csv").exists():
        horarios.construir()
    h = pd.read_csv(CLEAN / "horarios_nominal.csv")
    filas = []
    for (linea, sentido, serv), g in h.groupby(["linea", "sentido", "servicio"]):
        g = g.sort_values("orden")
        tid = f"{linea}-{sentido}-{serv}"
        uni = g["unidad"].iloc[0]
        for _, r in g.iterrows():
            filas.append({"linea": linea, "tren_id": tid, "sentido": sentido, "unidad": uni,
                          "estacion": r.estacion, "dist_km": r.dist_km, "hora_min": r.llegada_min})
            if r.salida_min != r.llegada_min:   # detencion -> segmento horizontal
                filas.append({"linea": linea, "tren_id": tid, "sentido": sentido, "unidad": uni,
                              "estacion": r.estacion, "dist_km": r.dist_km, "hora_min": r.salida_min})
    df = pd.DataFrame(filas)
    df.to_csv(CLEAN / "malla_real.csv", index=False)
    return df


if __name__ == "__main__":
    df = generar()
    for linea in ["L2", "L1"]:
        g = df[df.linea == linea]
        print(f"{linea}: {g['tren_id'].nunique()} trenes, {len(g)} puntos")
    print("Guardado malla_real.csv (con detenciones).")
