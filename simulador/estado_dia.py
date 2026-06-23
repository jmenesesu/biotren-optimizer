"""Estado del sistema segundo a segundo (situacion actual, Lun-Vie).

Cada uno de los 16 automotores esta SIEMPRE ubicado: en circulacion (sobre la via,
posicion interpolada entre estaciones) o estacionado en su cochera. La disposicion
inicial (al amanecer) proviene del grafico de rotaciones (pag. 16 del itinerario,
"Lunes a Jueves"); entre servicios el automotor queda en la cochera de la estacion
donde termino el servicio anterior.

API:
  cargar() -> (unidades, servicios)
  estado(t, unidades) -> {"trenes":[...circulando...], "estacionados":[...en cochera...]}
  grilla(step_s) -> DataFrame (alimenta la animacion)
"""
import sys
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO / "parsers"))
sys.path.append(str(REPO / "optimizador"))
from config import CLEAN  # noqa: E402
from ejes_distancia import eje_L1, eje_L2  # noqa: E402
import cocheras as cmod  # noqa: E402

DIA = "Lun-Vie"


def _dist_maps():
    return {"L1": dict(zip(eje_L1().estacion, eje_L1().dist_km)),
            "L2": dict(zip(eje_L2().estacion, eje_L2().dist_km))}


def _coch_info():
    c = pd.read_csv(CLEAN / "cocheras.csv")
    return {r.codigo: (r.estacion, r.linea, float(r.km)) for r in c.itertuples()}


def cargar():
    hl = pd.read_csv(CLEAN / "horarios_limpios.csv")
    dm = _dist_maps()
    p = hl[(hl.fuente == "pasajeros") & (hl.tipo_dia == DIA) & (hl.unidad != "")].copy()
    servicios = []
    for (u, serv, sent, tramo), g in p.groupby(["unidad", "servicio", "sentido", "tramo"]):
        g = g.sort_values("orden")
        dist = g.estacion.map(dm.get(tramo, {}))
        pts = []
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
    unidades = {}
    for u in sorted(set(s["unidad"] for s in servicios)):
        unidades[u] = sorted([s for s in servicios if s["unidad"] == u], key=lambda x: x["ini"])
    # asegurar que TODOS los automotores con disposicion inicial existan (aunque sin servicios)
    for u in cmod.DISPOSICION_INICIAL:
        unidades.setdefault(u, [])
    return unidades, servicios


def _pos(serv, t):
    pts = serv["pts"]
    for i in range(len(pts) - 1):
        (t0, d0, _), (t1, d1, _) = pts[i], pts[i + 1]
        if t0 - 1e-9 <= t <= t1 + 1e-9:
            return d0 if t1 == t0 else d0 + (d1 - d0) * (t - t0) / (t1 - t0)
    return None


def estado(t, unidades, coch=None):
    if coch is None:
        coch = _coch_info()
    trenes, estac = [], []
    for u, sv in unidades.items():
        run = next((s for s in sv if s["ini"] - 1e-9 <= t <= s["fin"] + 1e-9), None)
        if run is not None:
            d = _pos(run, t)
            if d is not None:
                trenes.append({"unidad": u, "servicio": run["servicio"], "tramo": run["tramo"],
                               "sentido": run["sentido"], "dist_km": round(d, 3)})
                continue
        # estacionado: antes del primer servicio -> disposicion inicial;
        # despues -> cochera de la estacion donde termino el ultimo servicio.
        if not sv or t < sv[0]["ini"]:
            code = cmod.DISPOSICION_INICIAL.get(u)
        else:
            prev = [s for s in sv if s["fin"] <= t]
            est = prev[-1]["est_fin"] if prev else sv[0]["est_ini"]
            code = cmod.LAYOVER_A_COCHERA.get(est) or cmod.DISPOSICION_INICIAL.get(u)
        if code and code in coch:
            est_nom, linea, km = coch[code]
            estac.append({"unidad": u, "cochera": code, "linea": linea, "dist_km": km})
        else:
            estac.append({"unidad": u, "cochera": code or "?", "linea": "", "dist_km": None})
    return {"trenes": trenes, "estacionados": estac}


def grilla(step_s=120):
    unidades, servicios = cargar()
    coch = _coch_info()
    t0 = min(s["ini"] for s in servicios)
    t1 = max(s["fin"] for s in servicios)
    filas = []
    t = (int(t0 * 60) // step_s) * step_s
    while t <= t1 * 60 + step_s:
        tm = t / 60.0
        st = estado(tm, unidades, coch)
        for tr in st["trenes"]:
            filas.append({"t_s": t, "unidad": tr["unidad"], "servicio": tr["servicio"],
                          "tramo": tr["tramo"], "sentido": tr["sentido"], "dist_km": tr["dist_km"],
                          "estado": "circulando", "cochera": ""})
        for e in st["estacionados"]:
            filas.append({"t_s": t, "unidad": e["unidad"], "servicio": "", "tramo": e["linea"],
                          "sentido": "", "dist_km": e["dist_km"], "estado": "cochera", "cochera": e["cochera"]})
        t += step_s
    df = pd.DataFrame(filas)
    df.to_csv(CLEAN / "estado_grilla.csv", index=False)
    return df


if __name__ == "__main__":
    unidades, servicios = cargar()
    g = grilla(120)
    coch = _coch_info()
    st = estado(5 * 60 + 0, unidades, coch)  # 05:00, antes de servicios
    from collections import Counter
    disp = Counter(e["cochera"] for e in st["estacionados"])
    print(f"Automotores: {len(unidades)} | servicios: {len(servicios)} | grilla: {len(g)} filas")
    print(f"Disposición 05:00 (debe ser CW=4, CC=2, LM=2, GU=3...): {dict(disp)}")
    print(f"Circulando 05:00: {len(st['trenes'])}, estacionados: {len(st['estacionados'])} (suma={len(st['trenes'])+len(st['estacionados'])})")
