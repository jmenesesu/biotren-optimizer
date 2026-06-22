"""Mapea los trenes de CARGA al km maestro de cada linea (consistente con pax).

Para cada tren y linea, resuelve cada estacion a su km maestro, ordena por tiempo,
y fuerza trayectoria monotona (descarta zigzag de rutas mezcladas/continuaciones).

Salida:
    datos/clean/malla_carga.csv  (linea, tren_id, portador, dist_km, hora_min)
"""
import sys
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO / "parsers"))
import estaciones_maestro as em  # noqa: E402
from config import CLEAN  # noqa: E402


def _monotona(pts):
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
    carga = pd.read_csv(f)
    carga = carga[carga.fuente == "carga"]
    filas = []
    for (portador, tren), g in carga.groupby(["portador", "servicio"]):
        g = g.sort_values("orden")
        for linea in ["L1", "L2"]:
            pts = []
            for _, r in g.iterrows():
                km = em.resolver_km(r.estacion, linea)
                if km is not None:
                    pts.append((km, float(r.llegada_min), r.estacion))
            pts.sort(key=lambda x: x[1])
            seen, limpio = set(), []
            for d, t, e in pts:
                if d in seen:
                    continue
                seen.add(d); limpio.append((d, t, e))
            mon = _monotona([(d, t) for d, t, e in limpio])
            mon_set = set((d, t) for d, t in mon)
            limpio = [(d, t, e) for d, t, e in limpio if (d, t) in mon_set]
            if len(limpio) < 2:
                continue
            for d, t, e in limpio:
                filas.append({"linea": linea, "tren_id": f"C-{portador}-{tren}",
                              "portador": portador, "estacion": e,
                              "dist_km": round(d, 3), "hora_min": round(t, 2)})
    out = pd.DataFrame(filas)
    out.to_csv(CLEAN / "malla_carga.csv", index=False)
    return out


if __name__ == "__main__":
    import numpy as np
    out = generar()
    print(f"Trenes de carga: {out['tren_id'].nunique() if len(out) else 0}")
    if len(out):
        print(out.groupby('linea')['tren_id'].nunique().to_string())
        bad = sum(1 for _, g in out.groupby(['tren_id', 'linea'])
                  if not (all(np.diff(g.sort_values('hora_min')['dist_km']) >= -1e-6)
                          or all(np.diff(g.sort_values('hora_min')['dist_km']) <= 1e-6)))
        print("no monotonos:", bad)
        print("dist L2 presentes:", sorted(out[out.linea=='L2'].dist_km.unique())[:12])
