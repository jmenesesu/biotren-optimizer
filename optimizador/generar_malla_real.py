"""Genera la malla del ITINERARIO ACTUAL (as-is) para el diagrama de Marey.

Usa las salidas reales por servicio (parse_itinerario_real) y propaga cada tren
sobre el eje espacial de su linea con los tiempos de viaje y detencion REALES del
itinerario (que el motor a 200 A reproduce dentro de ~2%). Resultado: la malla
real del dia, sentido por sentido, sobre un unico eje espacial.

Salida:
    datos/clean/malla_real.csv  (linea, tren_id, sentido, estacion, dist_km, hora_min)
"""
import sys
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO / "parsers"))
from config import CLEAN  # noqa: E402
from ejes_distancia import eje_L1, eje_L2  # noqa: E402

# sentido que recorre el eje en orden creciente de distancia
CRECE = {"L2": "CC->CW", "L1": "TH->LJ"}


def _tiempos(itin, linea, sentido):
    sub = itin[(itin.tramo == linea) & (itin.sentido == sentido)]
    return dict(zip(sub["estacion"], (sub["t_viaje_s"].fillna(0) + sub["detencion_s"].fillna(0)) / 60.0))


def generar():
    sal = pd.read_csv(CLEAN / "salidas_reales.csv")
    itin = pd.read_csv(CLEAN / "itinerario_tiempos.csv")
    ejes = {"L2": eje_L2(), "L1": eje_L1()}
    filas = []
    for linea in ["L2", "L1"]:
        eje = ejes[linea]
        estaciones = list(eje["estacion"])
        distkm = dict(zip(eje["estacion"], eje["dist_km"]))
        for sentido in sal[sal.linea == linea]["sentido"].unique():
            orden = estaciones if sentido == CRECE[linea] else list(reversed(estaciones))
            tmap = _tiempos(itin, linea, sentido)
            cum = [0.0]
            for s in orden[1:]:
                cum.append(cum[-1] + tmap.get(s, 1.0))
            sub = sal[(sal.linea == linea) & (sal.sentido == sentido)]
            for _, r in sub.iterrows():
                for s, c in zip(orden, cum):
                    filas.append({
                        "linea": linea, "tren_id": f"{linea}-{r.servicio}",
                        "sentido": sentido, "estacion": s,
                        "dist_km": round(distkm[s], 3),
                        "hora_min": round(r.salida_min + c, 2),
                    })
    df = pd.DataFrame(filas)
    df.to_csv(CLEAN / "malla_real.csv", index=False)
    return df


if __name__ == "__main__":
    df = generar()
    for linea in ["L2", "L1"]:
        g = df[df.linea == linea]
        print(f"{linea}: {g['tren_id'].nunique()} trenes (itinerario real), "
              f"hora {g['hora_min'].min():.0f}..{g['hora_min'].max():.0f} min")
    print(f"Filas: {len(df)} | Guardado: {CLEAN/'malla_real.csv'}")
