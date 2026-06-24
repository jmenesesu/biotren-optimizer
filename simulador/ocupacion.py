"""Modelo estructural de ocupación de bloques (cantones) — vía única exclusiva.

Recurso exclusivo = cada segmento de VÍA ÚNICA entre dos puntos de cruce (una
estación con apartadero o el inicio de la doble vía). En ese segmento solo puede
haber UN tren a la vez (cualquier sentido). Los cruzamientos se resuelven en los
puntos de cruce: si dos trenes ocuparían el mismo segmento único en ventanas que
se solapan, el que llega después ESPERA en el punto de entrada hasta liberarlo.

Esto impide estructuralmente que dos trenes en sentido opuesto compartan una vía
única. Produce un itinerario resuelto que alimenta la simulación en vivo.

Salida:
    datos/clean/horarios_resueltos.csv
    datos/clean/ocupacion_conflictos.csv
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
CLEAR = 0.5     # min de margen de liberación
TOL = 1.5       # tolerancia de solape por interpolación lineal (desaceleración)


def _bloques_unicos(linea, eje, tv):
    """Segmentos de vía única partidos en las estaciones interiores (puntos de cruce)."""
    unicas = [(r.km_lo, r.km_hi) for r in tv[(tv.linea == linea) & (tv.tipo == "única")].itertuples()]
    ests = sorted(eje.dist_km.tolist())
    bloques = []
    for lo, hi in unicas:
        cortes = [lo] + [k for k in ests if lo + 1e-3 < k < hi - 1e-3] + [hi]
        cortes = sorted(set(round(c, 3) for c in cortes))
        for i in range(len(cortes) - 1):
            if cortes[i + 1] - cortes[i] > 0.05:
                bloques.append((cortes[i], cortes[i + 1]))
    return bloques


def _t_en(paradas, d, delay=0.0):
    """tiempo (con delay) en que el tren pasa por el km d (interpolación)."""
    for i in range(len(paradas) - 1):
        a, b = paradas[i], paradas[i + 1]
        lo, hi = sorted([a["km"], b["km"]])
        if lo - 1e-9 <= d <= hi + 1e-9 and hi > lo:
            t = a["sal"] + (b["lleg"] - a["sal"]) * (d - a["km"]) / (b["km"] - a["km"])
            return t + delay
    return None


def resolver():
    hl = pd.read_csv(CLEAN / "horarios_limpios.csv")
    tv = pd.read_csv(CLEAN / "tramos_via.csv")
    ejes = {"L1": eje_L1(), "L2": eje_L2()}
    resueltos = hl.copy()
    conflictos = []

    for linea in ["L2", "L1"]:
        eje = ejes[linea]
        dist = dict(zip(eje.estacion, eje.dist_km))
        bloques = _bloques_unicos(linea, eje, tv)
        pax = hl[(hl.fuente == "pasajeros") & (hl.tipo_dia == DIA) & (hl.tramo == linea)].copy()
        if pax.empty:
            continue
        trenes = []
        for (sent, serv), g in pax.groupby(["sentido", "servicio"]):
            g = g.sort_values("orden")
            paradas = [{"idx": r.Index, "est": r.estacion, "km": dist.get(r.estacion),
                        "lleg": float(r.llegada_min), "sal": float(r.salida_min)}
                       for r in g.itertuples() if dist.get(r.estacion) is not None]
            if len(paradas) >= 2:
                trenes.append({"tid": f"{linea}-{sent}-{serv}", "sent": sent, "paradas": paradas,
                               "salida0": paradas[0]["sal"]})
        trenes.sort(key=lambda t: t["salida0"])

        reservas = {b: [] for b in bloques}
        for tr in trenes:
            P = tr["paradas"]
            delay = 0.0
            for (blo, bhi) in bloques:
                # tiempos ORIGINALES (sin delay) del cruce del bloque
                o_in = _t_en(P, blo, 0.0); o_out = _t_en(P, bhi, 0.0)
                if o_in is None or o_out is None:
                    continue
                a, b = min(o_in, o_out), max(o_in, o_out)
                # esperar a que liberen los trenes OPUESTOS ya reservados (tiempos originales)
                w = 0.0
                for (z0, z1, zsent) in reservas[(blo, bhi)]:
                    if zsent != tr["sent"] and a + w < z1 + CLEAR and b + w > z0 - CLEAR:
                        w = max(w, z1 + CLEAR - a)
                if w > 0.01:
                    conflictos.append({"linea": linea, "bloque_km": f"{blo:.1f}-{bhi:.1f}",
                                       "tren": tr["tid"], "espera_min": round(w, 1),
                                       "estacion_espera": min([p for p in P if p["km"] <= max(blo, bhi) + 1e-6],
                                                              key=lambda p: abs(p["km"] - blo), default=P[0])["est"],
                                       "hora": round(a, 1)})
                    delay = max(delay, w)
                reservas[(blo, bhi)].append((a, b, tr["sent"]))   # reservar tiempos ORIGINALES (no cascada)
            for p in P:
                resueltos.at[p["idx"], "llegada_min"] = round(p["lleg"] + delay, 2)
                resueltos.at[p["idx"], "salida_min"] = round(p["sal"] + delay, 2)

    def hm(x):
        if pd.isna(x):
            return ""
        h = int(x // 60) % 24; m = int(round(x % 60))
        return f"{(h + (1 if m == 60 else 0)) % 24:02d}:{0 if m == 60 else m:02d}"
    resueltos["llegada"] = resueltos["llegada_min"].map(hm)
    resueltos["salida"] = resueltos["salida_min"].map(hm)
    resueltos.to_csv(CLEAN / "horarios_resueltos.csv", index=False)
    cf = pd.DataFrame(conflictos)
    cf.to_csv(CLEAN / "ocupacion_conflictos.csv", index=False)
    return resueltos, cf


if __name__ == "__main__":
    res, cf = resolver()
    print(f"Itinerario resuelto: {len(res)} filas")
    print(f"Cruzamientos en vía única resueltos: {len(cf)}")
    if len(cf):
        print(f"  espera total {cf.espera_min.sum():.1f} min, máx {cf.espera_min.max():.1f} min")
        print(cf.groupby('linea').agg(n=('tren','size'), max=('espera_min','max')).to_string())
