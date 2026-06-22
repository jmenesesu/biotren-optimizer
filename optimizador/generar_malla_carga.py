"""Mapea los trenes de CARGA al eje de L1 y L2 usando la tabla maestra de km.

Reconcilia los nombres de carga con los de la red via estaciones_maestro
(codigo/km de OpenTrack). Para cada tren y cada linea, ordena por km y fuerza
trayectoria monotona (descarta el zigzag por rutas mezcladas o continuaciones).

Salida:
    datos/clean/malla_carga.csv  (linea, tren_id, portador, dist_km, hora_min)
"""
import sys
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO / "parsers"))
from config import CLEAN  # noqa: E402
from ejes_distancia import eje_L1, eje_L2  # noqa: E402
import estaciones_maestro as em  # noqa: E402


def _eje_dist_por_codigo():
    """codigo de estacion -> (linea, dist en el eje del passenger Marey)."""
    out = {}
    for linea, eje in [("L1", eje_L1()), ("L2", eje_L2())]:
        for _, r in eje.iterrows():
            res = em.resolver(r["estacion"], "L1" if linea == "L1" else "L2")
            if res:
                out[(res[0], linea)] = r["dist_km"]
    return out


def _monotona(pts):
    """pts ordenados por tiempo -> mayor subsecuencia sin cambio de direccion."""
    if len(pts) < 2:
        return pts
    signo = 1 if pts[-1][0] >= pts[0][0] else -1
    out = [pts[0]]
    for d, t in pts[1:]:
        if (d - out[-1][0]) * signo >= -1e-6:
            out.append((d, t))
    return out


def generar():
    f = CLEAN / "horarios_limpios.csv"
    if not f.exists():
        return pd.DataFrame()
    df = pd.read_csv(f)
    carga = df[df.fuente == "carga"]
    cod2dist = _eje_dist_por_codigo()
    filas = []
    for (portador, tren), g in carga.groupby(["portador", "servicio"]):
        g = g.sort_values("orden")
        # resolver cada estacion a codigo+grupo
        resueltas = []
        for _, r in g.iterrows():
            res = em.resolver(r["estacion"])
            if res:
                resueltas.append((res[0], res[1], float(r["llegada_min"])))
        for linea in ["L1", "L2"]:
            pts = [(cod2dist[(code, linea)], t) for code, grupo, t in resueltas
                   if (code, linea) in cod2dist]
            # dedup por codigo (quedarse con el primer tiempo) y ordenar por tiempo
            seen = set(); limpio = []
            for d, t in pts:
                if d in seen:
                    continue
                seen.add(d); limpio.append((d, t))
            limpio.sort(key=lambda x: x[1])
            limpio = _monotona(limpio)
            if len(limpio) < 2:
                continue
            for d, t in limpio:
                filas.append({"linea": linea, "tren_id": f"C-{portador}-{tren}",
                              "portador": portador, "dist_km": round(d, 3), "hora_min": round(t, 2)})
    out = pd.DataFrame(filas)
    out.to_csv(CLEAN / "malla_carga.csv", index=False)
    return out


if __name__ == "__main__":
    out = generar()
    import numpy as np
    print(f"Trenes de carga en eje: {out['tren_id'].nunique() if len(out) else 0}")
    if len(out):
        print(out.groupby('linea')['tren_id'].nunique().to_string())
        bad = 0
        for tid, g in out.groupby(['tren_id', 'linea']):
            d = g.sort_values('hora_min')['dist_km'].values
            if not (all(np.diff(d) >= -1e-6) or all(np.diff(d) <= 1e-6)):
                bad += 1
        print("segmentos NO monotonos:", bad, "(debe ser 0)")
