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
    global _HOLDS
    try:
        _HOLDS = _ocupacion(unidades)
    except Exception:
        _HOLDS = {}
    return unidades, servicios


def _perfil(d0, d1, t0, t1, t):
    """Posición con perfil trapezoidal: acelera al salir, crucero, frena al llegar.
    Reemplaza la interpolación lineal (velocidad constante)."""
    T = t1 - t0
    D = d1 - d0
    if T <= 1e-9:
        return d1
    x = t - t0
    ta = min(0.7, T / 2.0)   # min acelerando
    td = min(0.7, T / 2.0)   # min frenando
    base = T - (ta + td) / 2.0
    vp = D / base if abs(base) > 1e-9 else D / T   # velocidad de crucero (km/min)
    if x <= ta:
        s = 0.5 * (vp / ta) * x * x
    elif x <= T - td:
        s = 0.5 * vp * ta + vp * (x - ta)
    else:
        tau = x - (T - td)
        s = 0.5 * vp * ta + vp * (T - ta - td) + vp * tau - 0.5 * (vp / td) * tau * tau
    return d0 + s


def _pos(serv, t):
    pts = serv["pts"]
    for i in range(len(pts) - 1):
        (t0, d0, _), (t1, d1, _) = pts[i], pts[i + 1]
        if t0 - 1e-9 <= t <= t1 + 1e-9:
            if d1 == d0 or t1 == t0:      # detención en estación: queda quieto
                return d0
            return _perfil(d0, d1, t0, t1, t)
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
                # exclusividad de vía única: retener en el borde si un opuesto ocupa el bloque
                tid = f"{run['sentido']}-{run['servicio']}-{u}"
                for (lo, hi), (hu, entry) in _HOLDS.get(tid, {}).items():
                    if lo - 1e-6 <= d <= hi + 1e-6 and t < hu:
                        d = entry
                        break
                trenes.append({"unidad": u, "servicio": run["servicio"], "tramo": run["tramo"],
                               "sentido": run["sentido"], "dist_km": round(d, 3)})
                continue
        # estacionado: antes del primer servicio -> disposicion inicial;
        # despues -> cochera de la estacion donde termino el ultimo servicio.
        if not sv or t < sv[0]["ini"]:
            code = cmod.DISPOSICION_INICIAL.get(u)          # amanecida
        elif t > sv[-1]["fin"]:
            code = (cmod.DISPOSICION_FINAL.get(u)           # fin de día
                    or cmod.LAYOVER_A_COCHERA.get(sv[-1]["est_fin"])
                    or cmod.DISPOSICION_INICIAL.get(u))
        else:
            prev = [s for s in sv if s["fin"] <= t]         # entre servicios
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

def _bloques_unicos(linea, eje):
    import pandas as _pd
    tv = _pd.read_csv(CLEAN / "tramos_via.csv")
    unicas = [(r.km_lo, r.km_hi) for r in tv[(tv.linea == linea) & (tv.tipo == "única")].itertuples()]
    ests = sorted(eje.dist_km.tolist())
    bloques = []
    for lo, hi in unicas:
        cortes = sorted(set([round(lo, 3)] + [round(k, 3) for k in ests if lo + 1e-3 < k < hi - 1e-3] + [round(hi, 3)]))
        for i in range(len(cortes) - 1):
            if cortes[i + 1] - cortes[i] > 0.05:
                bloques.append((cortes[i], cortes[i + 1]))
    return bloques


def _t_en_pts(pts, d):
    for i in range(len(pts) - 1):
        (t0, d0, _), (t1, d1, _) = pts[i], pts[i + 1]
        lo, hi = sorted([d0, d1])
        if lo - 1e-9 <= d <= hi + 1e-9 and d1 != d0:
            return t0 + (t1 - t0) * (d - d0) / (d1 - d0)
    return None


def _ocupacion(unidades):
    """Por línea y bloque de vía única: retenciones por exclusividad (cruce opuesto).
    Devuelve dict serv_tid -> {(lo,hi): hold_until} (tiempo hasta el que el tren
    debe esperar en el borde de entrada por un opuesto que entró antes)."""
    ejes = {"L1": eje_L1(), "L2": eje_L2()}
    holds = {}
    for linea in ["L2", "L1"]:
        bloques = _bloques_unicos(linea, ejes[linea])
        # ocupaciones (serv, sentido, t_in, t_out, entry_km) por bloque
        items = {b: [] for b in bloques}
        servicios = []
        for u, sv in unidades.items():
            for s in sv:
                if s["tramo"] != linea:
                    continue
                tid = f"{s['sentido']}-{s['servicio']}-{u}"
                servicios.append((tid, s))
                for (lo, hi) in bloques:
                    ta = _t_en_pts(s["pts"], lo); tb = _t_en_pts(s["pts"], hi)
                    if ta is None or tb is None:
                        continue
                    t_in, t_out = min(ta, tb), max(ta, tb)
                    entry = lo if ta <= tb else hi
                    items[(lo, hi)].append([t_in, t_out, s["sentido"], tid, entry])
        # primero en entrar tiene prioridad; el resto se retiene si hay opuesto antes
        for b, lst in items.items():
            lst.sort(key=lambda x: x[0])
            for k in range(len(lst)):
                t_in, t_out, sent, tid, entry = lst[k]
                hu = 0.0
                for j in range(k):
                    z_in, z_out, zs, ztid, zent = lst[j]
                    # opuesto que entró antes (o a la vez) y aún ocupa el bloque
                    if zs != sent and z_out > t_in - 1e-6:
                        hu = max(hu, z_out)
                if hu > t_in + 0.01:
                    holds.setdefault(tid, {})[b] = (hu, entry)
    return holds


_HOLDS = {}
