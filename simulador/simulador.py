"""Simulador fixed-block (un tren por canton) del itinerario sobre la red.

Carga un itinerario (malla nominal) y mueve cada tren por sus cantones haciendo
cumplir la ocupacion:
  - canton 'single' (via unica): un solo tren a la vez (cualquier sentido).
  - canton 'double': multiples blocks de senal -> los trenes se siguen libremente.
Si un canton de via unica esta ocupado, el tren espera en el borde de entrada
(cruzamiento) y acumula demora (efecto cascada). Despacho FIFO por hora de salida.

Cambio de cabina: el canton de via unica adyacente a un terminal queda ocupado
tambien durante el cambio de cabina (CAMBIO_CABINA_MIN), reproduciendo el ciclo
real (p. ej. ~9 min en el Tunel Chepe = recorrido + cambio de cabina + holgura).

Salida:
    datos/clean/malla_sim.csv  (linea, tren_id, sentido, unidad, dist_km, hora_min)
    datos/clean/sim_eventos.csv
    datos/clean/sim_resumen.json
"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO / "parsers"))
from config import CLEAN  # noqa: E402

CLEARING_MIN = 1.5        # holgura de liberacion de canton de via unica (min)
CAMBIO_CABINA_MIN = 3.0   # cambio de cabina en cabezal (min)


def _interp(g, fronteras):
    d = g["dist_km"].to_numpy(); t = g["hora_min"].to_numpy()
    o = np.argsort(d)
    return dict(zip([round(x, 3) for x in fronteras], np.interp(fronteras, d[o], t[o])))


def simular(linea="L2"):
    malla = pd.read_csv(CLEAN / "malla_real.csv")
    blo = pd.read_csv(CLEAN / "bloques.csv")
    m = malla[malla.linea == linea].copy()
    b = blo[blo.linea == linea].sort_values("dist_lo").reset_index(drop=True)
    if m.empty or b.empty:
        return pd.DataFrame(), pd.DataFrame(), {}

    fronteras = sorted(set(b["dist_lo"]).union(set(b["dist_hi"])))
    dmin, dmax = min(fronteras), max(fronteras)

    trenes = []
    for tid, g in m.groupby("tren_id"):
        g = g.sort_values("hora_min")
        sent = g["sentido"].iloc[0]; uni = g["unidad"].iloc[0] if "unidad" in g else ""
        fr_t = _interp(g, fronteras)
        creciente = g["dist_km"].iloc[-1] > g["dist_km"].iloc[0]
        seq = b.iloc[::1] if creciente else b.iloc[::-1]
        cantones = []
        for _, r in seq.iterrows():
            lo, hi = round(r.dist_lo, 3), round(r.dist_hi, 3)
            t_lo, t_hi = fr_t[lo], fr_t[hi]
            borde_in = lo if creciente else hi
            borde_out = hi if creciente else lo
            terminus = (lo <= dmin + 1e-6) or (hi >= dmax - 1e-6)
            cantones.append({"block_id": r.block_id, "tipo": r.tipo,
                             "ent": min(t_lo, t_hi), "dur": abs(t_hi - t_lo),
                             "borde_in": borde_in, "borde_out": borde_out,
                             "terminus": terminus})
        trenes.append({"tid": tid, "sent": sent, "uni": uni,
                       "salida": g["hora_min"].min(), "cantones": cantones})

    trenes.sort(key=lambda x: x["salida"])

    reservas = {}   # block_id (single) -> lista de (t_in, t_out)
    filas, eventos = [], []
    for tr in trenes:
        demora = 0.0
        c0 = tr["cantones"][0]
        pts = [(c0["borde_in"], c0["ent"])]
        for c in tr["cantones"]:
            t_in_des = c["ent"] + demora
            t_in = t_in_des
            ocup = c["dur"]   # ocupacion del canton = tiempo de recorrido (el cambio
                              # de cabina ocurre en el anden, fuera del canton)
            if c["tipo"] == "single":
                ivs = reservas.setdefault(c["block_id"], [])
                cambio = True
                while cambio:
                    cambio = False
                    for (a, z) in ivs:
                        if t_in < z + CLEARING_MIN and t_in + ocup > a - CLEARING_MIN:
                            t_in = z + CLEARING_MIN; cambio = True
                ivs.append((t_in, t_in + ocup))
                espera = t_in - t_in_des
                if espera > 0.05:
                    eventos.append({"linea": linea, "tren_id": tr["tid"], "canton": c["block_id"],
                                    "espera_min": round(espera, 1), "hora": round(t_in, 1),
                                    "motivo": "cruzamiento/ocupación vía única"})
                    demora += espera
                    pts.append((c["borde_in"], t_in))     # hold (cruzamiento)
            t_out = t_in + c["dur"]
            pts.append((c["borde_out"], t_out))
        for d, t in pts:
            filas.append({"linea": linea, "tren_id": tr["tid"], "sentido": tr["sent"],
                          "unidad": tr["uni"], "dist_km": round(d, 3), "hora_min": round(t, 2)})

    df = pd.DataFrame(filas); df.to_csv(CLEAN / "malla_sim.csv", index=False)
    ev = pd.DataFrame(eventos); ev.to_csv(CLEAN / "sim_eventos.csv", index=False)
    resumen = {"linea": linea, "trenes": len(trenes), "eventos_espera": len(ev),
               "espera_total_min": round(ev["espera_min"].sum(), 1) if len(ev) else 0.0,
               "esperas_via_unica": len(ev),
               "clearing_min": CLEARING_MIN, "cambio_cabina_min": CAMBIO_CABINA_MIN,
               "nota_cabina": "El cambio de cabina (3 min) es restriccion de rotacion en el anden (ya reflejada en los horarios del itinerario), no ocupa el canton de via unica."}
    with open(CLEAN / "sim_resumen.json", "w", encoding="utf-8") as fh:
        json.dump(resumen, fh, ensure_ascii=False, indent=2)
    return df, ev, resumen


if __name__ == "__main__":
    df, ev, res = simular("L2")
    print(json.dumps(res, ensure_ascii=False, indent=2))
    if len(ev):
        print(f"\nEsperas en vía única: {len(ev)} | total {res['espera_total_min']} min "
              f"| max {ev['espera_min'].max()} min")
        print(ev.sort_values('espera_min', ascending=False).head(6).to_string(index=False))
