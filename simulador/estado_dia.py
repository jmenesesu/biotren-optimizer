"""Estado del sistema segundo a segundo (situacion actual, Lun-Vie).

Reconstruye, para cualquier instante t (minutos desde 00:00, resolucion segundos),
la posicion de cada automotor y la ocupacion de cocheras, a partir de la rotacion
de unidades en horarios_limpios.

- Cada automotor tiene una linea de tiempo: tramos en circulacion (un servicio) y
  tramos estacionado (entre servicios, en la estacion donde termino el anterior).
- En circulacion la posicion se interpola linealmente entre estaciones (el itinerario
  da llegada/salida por estacion; entre ellas se asume velocidad constante).

API:
  cargar(malla="horarios") -> (unidades, servicios)
  estado(t, unidades) -> {"trenes": [...], "cocheras": {estacion: [unidad,...]}}
  grilla(step_s=60) -> DataFrame con la posicion de cada unidad en una grilla de t
"""
import sys
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO / "parsers"))
sys.path.append(str(REPO / "optimizador"))
from config import CLEAN  # noqa: E402
from ejes_distancia import eje_L1, eje_L2  # noqa: E402

DIA = "Lun-Vie"


def _dist_maps():
    return {"L1": dict(zip(eje_L1().estacion, eje_L1().dist_km)),
            "L2": dict(zip(eje_L2().estacion, eje_L2().dist_km))}


def cargar():
    hl = pd.read_csv(CLEAN / "horarios_limpios.csv")
    dm = _dist_maps()
    p = hl[(hl.fuente == "pasajeros") & (hl.tipo_dia == DIA) & (hl.unidad != "")].copy()
    servicios = []
    for (u, serv, sent, tramo), g in p.groupby(["unidad", "servicio", "sentido", "tramo"]):
        g = g.sort_values("orden")
        dist = g.estacion.map(dm.get(tramo, {}))
        pts = []   # (t, dist) por llegada y salida
        for est, l, s, d in zip(g.estacion, g.llegada_min, g.salida_min, dist):
            if pd.isna(d):
                continue
            pts.append((float(l), float(d), est))
            if s != l:
                pts.append((float(s), float(d), est))
        if len(pts) < 2:
            continue
        servicios.append({"unidad": u, "servicio": str(serv), "sentido": sent, "tramo": tramo,
                          "ini": pts[0][0], "fin": pts[-1][0],
                          "est_ini": pts[0][2], "est_fin": pts[-1][2], "pts": pts})
    # linea de tiempo por unidad
    unidades = {}
    for u in sorted(set(s["unidad"] for s in servicios)):
        sv = sorted([s for s in servicios if s["unidad"] == u], key=lambda x: x["ini"])
        unidades[u] = sv
    return unidades, servicios


def _pos(serv, t):
    pts = serv["pts"]
    for i in range(len(pts) - 1):
        (t0, d0, _), (t1, d1, _) = pts[i], pts[i + 1]
        if t0 - 1e-9 <= t <= t1 + 1e-9:
            if t1 == t0:
                return d0
            return d0 + (d1 - d0) * (t - t0) / (t1 - t0)
    return None


def estado(t, unidades):
    trenes, cocheras = [], {}
    for u, sv in unidades.items():
        corriendo = None
        for s in sv:
            if s["ini"] - 1e-9 <= t <= s["fin"] + 1e-9:
                corriendo = s
                break
        if corriendo:
            d = _pos(corriendo, t)
            if d is not None:
                trenes.append({"unidad": u, "servicio": corriendo["servicio"],
                               "tramo": corriendo["tramo"], "sentido": corriendo["sentido"],
                               "dist_km": round(d, 3)})
                continue
        # estacionado: estacion del servicio anterior (o el primero si aun no parte)
        prev = [s for s in sv if s["fin"] <= t]
        est = prev[-1]["est_fin"] if prev else (sv[0]["est_ini"] if sv else "?")
        cocheras.setdefault(est, []).append(u)
    return {"trenes": trenes, "cocheras": cocheras}


def grilla(step_s=60):
    unidades, servicios = cargar()
    t0 = min(s["ini"] for s in servicios)
    t1 = max(s["fin"] for s in servicios)
    filas = []
    t = (int(t0 * 60) // step_s) * step_s
    while t <= t1 * 60 + step_s:
        tm = t / 60.0
        st = estado(tm, unidades)
        for tr in st["trenes"]:
            filas.append({"t_min": round(tm, 3), "t_s": t, "unidad": tr["unidad"],
                          "servicio": tr["servicio"], "tramo": tr["tramo"],
                          "sentido": tr["sentido"], "dist_km": tr["dist_km"], "estado": "circulando"})
        for est, us in st["cocheras"].items():
            for u in us:
                filas.append({"t_min": round(tm, 3), "t_s": t, "unidad": u, "servicio": "",
                              "tramo": "", "sentido": "", "dist_km": None,
                              "estado": f"cochera:{est}"})
        t += step_s
    df = pd.DataFrame(filas)
    df.to_csv(CLEAN / "estado_grilla.csv", index=False)
    return df


def prefill_cocheras(sobrescribir=False):
    """Crea plantilla de cocheras con las estaciones de layover (para completar).
    No sobrescribe datos reales ya cargados salvo sobrescribir=True."""
    if (CLEAN / "cocheras.csv").exists() and not sobrescribir:
        return pd.read_csv(CLEAN / "cocheras.csv")
    unidades, servicios = cargar()
    from collections import Counter
    c = Counter(s["est_fin"] for s in servicios)
    dm = _dist_maps()
    rows = []
    for est, n in c.most_common():
        linea = "L2" if est in dm["L2"] else ("L1" if est in dm["L1"] else "?")
        rows.append({"estacion": est, "linea": linea, "nombre_cochera": "",
                     "capacidad": "", "layovers_dia": n})
    pd.DataFrame(rows).to_csv(CLEAN / "cocheras.csv", index=False)
    return pd.read_csv(CLEAN / "cocheras.csv")


if __name__ == "__main__":
    unidades, servicios = cargar()
    coch = prefill_cocheras()
    g = grilla(120)
    print(f"Automotores: {len(unidades)} | servicios: {len(servicios)} | "
          f"cocheras: {len(coch)} | grilla: {len(g)} filas (paso 120 s)")
