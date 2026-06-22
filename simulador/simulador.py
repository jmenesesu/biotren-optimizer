"""Simulador fixed-block (un tren por canton) — fuente: horarios_limpios.

Lee la tabla limpia (situacion actual, Lun-Vie, pasajeros) y simula la ocupacion
de los cantones de VIA UNICA: un solo tren a la vez; si esta ocupado, el tren
espera en la estacion de entrada (cruzamiento) y su programacion se desplaza.
La doble via se modela con multiples blocks (los trenes se siguen libremente).
El cambio de cabina es restriccion de rotacion en el anden (ya en los horarios).
Corre L2 y L1; los cantones provienen de las señales reales (bloques.py).

Salida:
    datos/clean/malla_sim.csv   (linea, tren_id, sentido, unidad, equipo_vacio,
                                 estacion, dist_km, hora_min)
    datos/clean/sim_eventos.csv ; datos/clean/sim_resumen.json (por linea)
"""
import json
import sys
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO / "parsers"))
sys.path.append(str(REPO / "optimizador"))
from config import CLEAN  # noqa: E402
from ejes_distancia import eje_L1, eje_L2  # noqa: E402

CLEARING_MIN = 1.5
DIA = "Lun-Vie"


def _t_en_dist(seq, d):
    for i in range(len(seq) - 1):
        a, b = seq[i], seq[i + 1]
        lo, hi = sorted([a["dist_km"], b["dist_km"]])
        if lo - 1e-6 <= d <= hi + 1e-6 and hi > lo:
            frac = (d - a["dist_km"]) / (b["dist_km"] - a["dist_km"])
            return a["salida_min"] + frac * (b["llegada_min"] - a["salida_min"])
    return None


def simular(linea):
    hl = pd.read_csv(CLEAN / "horarios_limpios.csv")
    blo = pd.read_csv(CLEAN / "bloques.csv")
    eje = eje_L2() if linea == "L2" else eje_L1()
    dist = dict(zip(eje["estacion"], eje["dist_km"]))
    H = hl[(hl.fuente == "pasajeros") & (hl.tipo_dia == DIA) & (hl.tramo == linea)].copy()
    H["dist_km"] = H["estacion"].map(dist)
    H = H.dropna(subset=["dist_km"])
    singles = blo[(blo.linea == linea) & (blo.tipo == "single")][["block_id", "dist_lo", "dist_hi"]]
    if H.empty:
        return pd.DataFrame(), pd.DataFrame(), {"linea": linea, "trenes": 0}

    trenes = []
    for (sent, serv), g in H.groupby(["sentido", "servicio"]):
        g = g.sort_values("orden")
        seq = g[["estacion", "dist_km", "llegada_min", "salida_min"]].to_dict("records")
        if len(seq) < 2:
            continue
        trenes.append({"tid": f"{linea}-{sent}-{serv}", "sent": sent,
                       "uni": g["unidad"].iloc[0], "vac": bool(g["equipo_vacio"].iloc[0]),
                       "salida": seq[0]["salida_min"], "seq": seq})
    trenes.sort(key=lambda x: x["salida"])

    reservas, eventos = {}, []
    for tr in trenes:
        seq = tr["seq"]
        for _, blk in singles.iterrows():
            t_lo, t_hi = _t_en_dist(seq, blk.dist_lo), _t_en_dist(seq, blk.dist_hi)
            if t_lo is None or t_hi is None:
                continue
            t_in, t_out = min(t_lo, t_hi), max(t_lo, t_hi)
            ivs = reservas.setdefault(blk.block_id, [])
            espera, cambio = 0.0, True
            while cambio:
                cambio = False
                for (a, z) in ivs:
                    if t_in + espera < z + CLEARING_MIN and t_out + espera > a - CLEARING_MIN:
                        espera = z + CLEARING_MIN - t_in; cambio = True
            ivs.append((t_in + espera, t_out + espera))
            if espera > 0.05:
                mid = (blk.dist_lo + blk.dist_hi) / 2
                i_entry = next((i for i in range(len(seq) - 1)
                                if min(seq[i]["dist_km"], seq[i + 1]["dist_km"]) <= mid
                                <= max(seq[i]["dist_km"], seq[i + 1]["dist_km"])), 0)
                eventos.append({"linea": linea, "tren_id": tr["tid"], "canton": blk.block_id,
                                "espera_min": round(espera, 1), "hora": round(t_in, 1),
                                "estacion_espera": seq[i_entry]["estacion"]})
                for k in range(i_entry, len(seq)):
                    if k > i_entry:
                        seq[k]["llegada_min"] += espera
                    seq[k]["salida_min"] += espera

    filas = []
    for tr in trenes:
        for r in tr["seq"]:
            filas.append({"linea": linea, "tren_id": tr["tid"], "sentido": tr["sent"],
                          "unidad": tr["uni"], "equipo_vacio": tr["vac"], "estacion": r["estacion"],
                          "dist_km": round(r["dist_km"], 3), "hora_min": round(r["llegada_min"], 2)})
            if r["salida_min"] != r["llegada_min"]:
                filas.append({"linea": linea, "tren_id": tr["tid"], "sentido": tr["sent"],
                              "unidad": tr["uni"], "equipo_vacio": tr["vac"], "estacion": r["estacion"],
                              "dist_km": round(r["dist_km"], 3), "hora_min": round(r["salida_min"], 2)})
    df = pd.DataFrame(filas)
    ev = pd.DataFrame(eventos)
    resumen = {"linea": linea, "trenes": len(trenes), "esperas_via_unica": len(ev),
               "espera_total_min": round(ev["espera_min"].sum(), 1) if len(ev) else 0.0,
               "espera_max_min": round(ev["espera_min"].max(), 1) if len(ev) else 0.0,
               "clearing_min": CLEARING_MIN, "fuente": "horarios_limpios"}
    return df, ev, resumen


def main():
    dfs, evs, resumenes = [], [], {}
    for linea in ["L2", "L1"]:
        df, ev, res = simular(linea)
        if not df.empty:
            dfs.append(df)
        if not ev.empty:
            evs.append(ev)
        resumenes[linea] = res
    malla = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
    malla.to_csv(CLEAN / "malla_sim.csv", index=False)
    eventos = pd.concat(evs, ignore_index=True) if evs else pd.DataFrame(
        columns=["linea", "tren_id", "canton", "espera_min", "hora", "estacion_espera"])
    eventos.to_csv(CLEAN / "sim_eventos.csv", index=False)
    with open(CLEAN / "sim_resumen.json", "w", encoding="utf-8") as fh:
        json.dump(resumenes, fh, ensure_ascii=False, indent=2)
    return resumenes


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False, indent=2))
