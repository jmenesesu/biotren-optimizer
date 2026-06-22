"""Mapea los trenes de CARGA al eje espacial de L1 para superponerlos en el Marey.

Toma la tabla limpia (horarios_limpios, fuente=carga), mapea sus estaciones a las
de L1 por nombre y arma la trayectoria (dist_km, hora_min) de cada tren que pase
por >=2 estaciones de L1. Asi se grafican diferenciados (gris, segmentado).

Salida:
    datos/clean/malla_carga.csv  (linea, tren_id, portador, estacion, dist_km, hora_min)
"""
import sys
import unicodedata
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO / "parsers"))
from config import CLEAN  # noqa: E402
from ejes_distancia import eje_L1  # noqa: E402


def _key(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().upper()
    return "".join(ch for ch in s if ch.isalnum())


def generar():
    f = CLEAN / "horarios_limpios.csv"
    if not f.exists():
        return pd.DataFrame()
    df = pd.read_csv(f)
    carga = df[df.fuente == "carga"]
    eje = eje_L1()
    dist = {_key(r.estacion): r.dist_km for _, r in eje.iterrows()}
    filas = []
    for (portador, tren), g in carga.groupby(["portador", "servicio"]):
        g = g.sort_values("orden")
        pts = [(dist[_key(r.estacion)], r.llegada_min) for _, r in g.iterrows()
               if _key(r.estacion) in dist]
        if len(pts) < 2:
            continue
        for d, t in pts:
            filas.append({"linea": "L1", "tren_id": f"C-{portador}-{tren}",
                          "portador": portador, "estacion": "", "dist_km": round(d, 3),
                          "hora_min": round(float(t), 2)})
    out = pd.DataFrame(filas)
    out.to_csv(CLEAN / "malla_carga.csv", index=False)
    return out


if __name__ == "__main__":
    out = generar()
    print(f"Trenes de carga en eje L1: {out['tren_id'].nunique() if len(out) else 0}")
    if len(out):
        print(out.groupby('portador')['tren_id'].nunique().to_string())
