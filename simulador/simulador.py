"""Simulador fixed-block (un tren por canton) del itinerario sobre la red.

Usa la base de horarios (llegada/salida por estacion, con detenciones) y hace
cumplir la ocupacion de los cantones de VIA UNICA: un solo tren a la vez. Si el
canton esta ocupado, el tren espera en la estacion de entrada (cruzamiento) y
toda su programacion posterior se desplaza (demora en cascada). La doble via se
modela con multiples blocks de senal (los trenes se siguen libremente).

El cambio de cabina es restriccion de rotacion en el anden (ya en los horarios),
no ocupa el canton.

Salida:
    datos/clean/malla_sim.csv   (linea, tren_id, sentido, unidad, estacion, dist_km, hora_min)
    datos/clean/sim_eventos.csv
    datos/clean/sim_resumen.json
"""
import json
import sys
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO / "parsers"))
from config import CLEAN  # noqa: E402

CLEARING_MIN = 1.5   # liberacion de canton de via unica (min)


def _t_en_dist(seq, d):
    """Tiempo al cruzar la distancia d, interpolando en el tramo de marcha."""
    for i in range(len(seq) - 1):
        a, b = seq[i], seq[i + 1]
        lo, hi = sorted([a["dist_km"], b["dist_km"]])
        if lo - 1e-6 <= d <= hi + 1e-6 and hi > lo:
            # tramo de marcha: salida de a -> llegada de b
            frac = (d - a["dist_km"]) / (b["dist_km"] - a["dist_km"])
            return a["salida_min"] + frac * (b["llegada_min"] - a["salida_min"])
    return None


def simular(linea="L2"):
    h = pd.read_csv(CLEAN / "horarios_nominal.csv")
    blo = pd.read_csv(CLEAN / "bloques.csv")
    H = h[h.linea == linea]
    singles = blo[(blo.linea == linea) & (blo.tipo == "single")][["block_id", "dist_lo", "dist_hi"]]
    if H.empty:
        return pd.DataFrame(), pd.DataFrame(), {}

    trenes = []
    for (sent, serv), g in H.groupby(["sentido", "servicio"]):
        g = g.sort_values("orden").reset_index(drop=True)
        seq = g[["estacion", "dist_km", "llegada_min", "salida_min"]].to_dict("records")
        trenes.append({"tid": f"{linea}-{sent}-{serv}", "sent": sent,
                       "uni": g["unidad"].iloc[0], "salida": seq[0]["salida_min"], "seq": seq})
    trenes.sort(key=lambda x: x["salida"])

    reservas = {}   # block_id -> [(t_in,t_out)]
    eventos = []
    for tr in trenes:
        seq = tr["seq"]
        for _, blk in singles.iterrows():
            lo, hi = blk.dist_lo, blk.dist_hi
            t_lo, t_hi = _t_en_dist(seq, lo), _t_en_dist(seq, hi)
            if t_lo is None or t_hi is None:
                continue
            t_in, t_out = min(t_lo, t_hi), max(t_lo, t_hi)
            ivs = reservas.setdefault(blk.block_id, [])
            espera = 0.0
            cambio = True
            while cambio:
                cambio = False
                for (a, z) in ivs:
                    if t_in + espera < z + CLEARING_MIN and t_out + espera > a - CLEARING_MIN:
                        espera = z + CLEARING_MIN - t_in; cambio = True
            ivs.append((t_in + espera, t_out + espera))
            if espera > 0.05:
                # estacion de entrada = la del tramo de marcha que cruza el canton
                i_entry = next((i for i in range(len(seq) - 1)
                                if min(seq[i]["dist_km"], seq[i + 1]["dist_km"]) <= (lo + hi) / 2
                                <= max(seq[i]["dist_km"], seq[i + 1]["dist_km"])), 0)
                eventos.append({"linea": linea, "tren_id": tr["tid"], "canton": blk.block_id,
                                "espera_min": round(espera, 1), "hora": round(t_in, 1),
                                "estacion_espera": seq[i_entry]["estacion"]})
                # desplazar la programacion desde la estacion de entrada en adelante
                for k in range(i_entry, len(seq)):
                    if k > i_entry:
                        seq[k]["llegada_min"] += espera
                    seq[k]["salida_min"] += espera

    filas = []
    for tr in trenes:
        for r in tr["seq"]:
            filas.append({"linea": linea, "tren_id": tr["tid"], "sentido": tr["sent"],
                          "unidad": tr["uni"], "estacion": r["estacion"],
                          "dist_km": r["dist_km"], "hora_min": round(r["llegada_min"], 2)})
            if r["salida_min"] != r["llegada_min"]:
                filas.append({"linea": linea, "tren_id": tr["tid"], "sentido": tr["sent"],
                              "unidad": tr["uni"], "estacion": r["estacion"],
                              "dist_km": r["dist_km"], "hora_min": round(r["salida_min"], 2)})
    df = pd.DataFrame(filas); df.to_csv(CLEAN / "malla_sim.csv", index=False)
    ev = pd.DataFrame(eventos); ev.to_csv(CLEAN / "sim_eventos.csv", index=False)
    resumen = {"linea": linea, "trenes": len(trenes), "esperas_via_unica": len(ev),
               "espera_total_min": round(ev["espera_min"].sum(), 1) if len(ev) else 0.0,
               "espera_max_min": round(ev["espera_min"].max(), 1) if len(ev) else 0.0,
               "clearing_min": CLEARING_MIN,
               "nota": "Ocupacion del canton de via unica = tiempo de recorrido; cambio de cabina es rotacion en anden (ya en horarios)."}
    with open(CLEAN / "sim_resumen.json", "w", encoding="utf-8") as fh:
        json.dump(resumen, fh, ensure_ascii=False, indent=2)
    return df, ev, resumen


if __name__ == "__main__":
    df, ev, res = simular("L2")
    print(json.dumps(res, ensure_ascii=False, indent=2))
