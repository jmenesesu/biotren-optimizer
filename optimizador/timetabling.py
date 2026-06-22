"""Optimizador de timetabling: reprograma SALIDAS para eliminar cruzamientos.

Toma los trenes de la situacion actual (horarios_limpios, Lun-Vie, pasajeros) con
sus tiempos de recorrido FIJOS, y decide un desfase entero de salida por tren
(delta, acotado) que evite el cruzamiento (ocupacion simultanea en sentidos
OPUESTOS) en cada seccion de via unica, minimizando la desviacion total respecto
al horario actual. MILP en PuLP/CBC.

Salida:
    datos/clean/malla_opt.csv     (horario reprogramado; columnas como malla_sim)
    datos/clean/opt_offsets.csv   (delta por tren)
    datos/clean/opt_resumen.json  (cruzamientos antes/despues, desviacion)
"""
import json
import sys
from pathlib import Path
import pandas as pd
import pulp

REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO / "parsers"))
from config import CLEAN  # noqa: E402
from ejes_distancia import eje_L1, eje_L2  # noqa: E402
from via_unica import VIA_UNICA  # noqa: E402

DIA = "Lun-Vie"
CLEAR = 1.5
DELTA = 12          # rango de desfase de salida permitido (+/- min)
TLIM = 60           # s por linea


def _t_en_dist(seq, d):
    for i in range(len(seq) - 1):
        a, b = seq[i], seq[i + 1]
        lo, hi = sorted([a["dist_km"], b["dist_km"]])
        if lo - 1e-6 <= d <= hi + 1e-6 and hi > lo:
            frac = (d - a["dist_km"]) / (b["dist_km"] - a["dist_km"])
            return a["salida_min"] + frac * (b["llegada_min"] - a["salida_min"])
    return None


def _trenes(linea):
    hl = pd.read_csv(CLEAN / "horarios_limpios.csv")
    eje = eje_L2() if linea == "L2" else eje_L1()
    dist = dict(zip(eje["estacion"], eje["dist_km"]))
    H = hl[(hl.fuente == "pasajeros") & (hl.tipo_dia == DIA) & (hl.tramo == linea)].copy()
    H["dist_km"] = H["estacion"].map(dist)
    H = H.dropna(subset=["dist_km"])
    trenes = []
    for (sent, serv), g in H.groupby(["sentido", "servicio"]):
        g = g.sort_values("orden")
        seq = g[["estacion", "dist_km", "llegada_min", "salida_min"]].to_dict("records")
        if len(seq) < 2:
            continue
        trenes.append({"tid": f"{linea}-{sent}-{serv}", "sent": sent, "serv": serv,
                       "uni": g["unidad"].iloc[0], "vac": bool(g["equipo_vacio"].iloc[0]),
                       "seq": seq})
    return trenes


def _ocupaciones(trenes, linea):
    sec = [(n, lo, hi) for n, lo, hi, bloq in VIA_UNICA.get(linea, []) if bloq]
    ocup = []
    for k, tr in enumerate(trenes):
        for n, lo, hi in sec:
            a, b = _t_en_dist(tr["seq"], lo), _t_en_dist(tr["seq"], hi)
            if a is None or b is None:
                continue
            ocup.append((k, n, min(a, b), max(a, b), tr["sent"]))
    return ocup


def _cruzamientos(ocup, offs):
    por_sec = {}
    for k, n, ti, to, se in ocup:
        por_sec.setdefault(n, []).append((ti + offs[k], to + offs[k], se))
    tot = 0
    for n, ivs in por_sec.items():
        for i in range(len(ivs)):
            for j in range(i + 1, len(ivs)):
                if ivs[i][2] == ivs[j][2]:
                    continue  # mismo sentido: se siguen, no es cruzamiento
                if ivs[j][0] < ivs[i][1] + CLEAR and ivs[i][0] < ivs[j][1] + CLEAR:
                    tot += 1
    return tot


def optimizar(linea):
    trenes = _trenes(linea)
    ocup = _ocupaciones(trenes, linea)
    n = len(trenes)
    cruz_antes = _cruzamientos(ocup, {k: 0.0 for k in range(n)})

    prob = pulp.LpProblem(f"tt_{linea}", pulp.LpMinimize)
    d = {k: pulp.LpVariable(f"d_{k}", -DELTA, DELTA, cat="Integer") for k in range(n)}
    a = {k: pulp.LpVariable(f"a_{k}", 0, DELTA, cat="Continuous") for k in range(n)}
    for k in range(n):
        prob += a[k] >= d[k]
        prob += a[k] >= -d[k]
    por_sec = {}
    for k, nsec, ti, to, se in ocup:
        por_sec.setdefault(nsec, []).append((k, ti, to, se))
    M = 4000
    npar = 0
    for nsec, lst in por_sec.items():
        for i in range(len(lst)):
            ki, ti, to_i, se_i = lst[i]
            for j in range(i + 1, len(lst)):
                kj, tj, to_j, se_j = lst[j]
                if se_i == se_j:
                    continue  # solo cruzamientos (sentidos opuestos)
                if tj - to_i > 2 * DELTA + CLEAR or ti - to_j > 2 * DELTA + CLEAR:
                    continue
                b = pulp.LpVariable(f"b_{nsec[:3]}_{ki}_{kj}", cat="Binary")
                prob += (tj + d[kj]) - (to_i + d[ki]) >= CLEAR - M * (1 - b)
                prob += (ti + d[ki]) - (to_j + d[kj]) >= CLEAR - M * b
                npar += 1
    prob += pulp.lpSum(a.values())
    prob.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=TLIM))
    estado = pulp.LpStatus[prob.status]
    offs = {k: (round(d[k].value()) if d[k].value() is not None else 0) for k in range(n)}
    cruz_desp = _cruzamientos(ocup, offs)
    desv = sum(abs(v) for v in offs.values())

    filas, off_rows = [], []
    for k, tr in enumerate(trenes):
        off = offs[k]
        off_rows.append({"linea": linea, "tren_id": tr["tid"], "sentido": tr["sent"],
                         "servicio": tr["serv"], "offset_min": off})
        for r in tr["seq"]:
            filas.append({"linea": linea, "tren_id": tr["tid"], "sentido": tr["sent"],
                          "unidad": tr["uni"], "equipo_vacio": tr["vac"], "estacion": r["estacion"],
                          "dist_km": round(r["dist_km"], 3), "hora_min": round(r["llegada_min"] + off, 2)})
            if r["salida_min"] != r["llegada_min"]:
                filas.append({"linea": linea, "tren_id": tr["tid"], "sentido": tr["sent"],
                              "unidad": tr["uni"], "equipo_vacio": tr["vac"], "estacion": r["estacion"],
                              "dist_km": round(r["dist_km"], 3), "hora_min": round(r["salida_min"] + off, 2)})
    resumen = {"linea": linea, "estado": estado, "trenes": n, "pares_restringidos": npar,
               "cruzamientos_antes": cruz_antes, "cruzamientos_despues": cruz_desp,
               "desviacion_total_min": desv,
               "trenes_reprogramados": sum(1 for v in offs.values() if v != 0),
               "desfase_max_min": max((abs(v) for v in offs.values()), default=0),
               "delta_permitido": DELTA, "clearing_min": CLEAR}
    return pd.DataFrame(filas), pd.DataFrame(off_rows), resumen


def main():
    mallas, offs, resumenes = [], [], {}
    for linea in ["L2", "L1"]:
        m, o, r = optimizar(linea)
        if not m.empty:
            mallas.append(m); offs.append(o)
        resumenes[linea] = r
    pd.concat(mallas, ignore_index=True).to_csv(CLEAN / "malla_opt.csv", index=False)
    pd.concat(offs, ignore_index=True).to_csv(CLEAN / "opt_offsets.csv", index=False)
    with open(CLEAN / "opt_resumen.json", "w", encoding="utf-8") as fh:
        json.dump(resumenes, fh, ensure_ascii=False, indent=2)
    return resumenes


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False, indent=2))
