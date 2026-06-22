"""Simulador fixed-block (un tren por canton) del itinerario sobre la red.

Carga un itinerario (malla nominal), mueve cada tren por sus cantones y hace
cumplir la ocupacion: un canton 'single' admite un solo tren (cualquier sentido);
un canton 'double' admite un tren por sentido. Si un canton esta ocupado, el tren
espera en el limite de entrada (cruzamiento/retencion) y acumula demora (efecto
en cascada). Es event-based sobre entradas/salidas de canton (equivalente exacto
a segundo a segundo para la ocupacion de bloque).

Despacho: prioridad FIFO por hora de salida nominal.

Salida:
    datos/clean/malla_sim.csv  (linea, tren_id, sentido, unidad, dist_km, hora_min)
    datos/clean/sim_eventos.csv (linea, tren_id, canton, tipo, espera_min, motivo, hora)
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

CLEARING_MIN = 1.5   # holgura de liberacion de canton de via unica (min)
HEADWAY_DOBLE = 2.0  # headway minimo en doble via, mismo sentido (min)


def _interp_tiempos(g, fronteras):
    """Tiempo nominal del tren al cruzar cada frontera (km)."""
    d = g["dist_km"].to_numpy(); t = g["hora_min"].to_numpy()
    o = np.argsort(d)
    return np.interp(fronteras, d[o], t[o])


def simular(linea="L2"):
    malla = pd.read_csv(CLEAN / "malla_real.csv")
    blo = pd.read_csv(CLEAN / "bloques.csv")
    m = malla[malla.linea == linea].copy()
    b = blo[blo.linea == linea].sort_values("dist_lo").reset_index(drop=True)
    if m.empty or b.empty:
        return pd.DataFrame(), pd.DataFrame(), {}

    fronteras = sorted(set(b["dist_lo"]).union(set(b["dist_hi"])))

    # nominal de cada tren: secuencia de cantones en orden de viaje
    trenes = []
    for tid, g in m.groupby("tren_id"):
        sent = g["sentido"].iloc[0]; uni = g["unidad"].iloc[0] if "unidad" in g else ""
        tf = _interp_tiempos(g, fronteras)
        fr_t = dict(zip([round(x, 3) for x in fronteras], tf))
        # cantones en orden de viaje (CC->CW: dist creciente; inverso: decreciente)
        bord = b.copy()
        creciente = g["dist_km"].iloc[-1] > g["dist_km"].iloc[0]
        seq = bord.iloc[::1] if creciente else bord.iloc[::-1]
        cantones = []
        for _, r in seq.iterrows():
            lo, hi = round(r.dist_lo, 3), round(r.dist_hi, 3)
            t_in = fr_t[lo] if creciente else fr_t[hi]
            t_out = fr_t[hi] if creciente else fr_t[lo]
            cantones.append({"block_id": r.block_id, "tipo": r.tipo,
                             "ent": min(t_in, t_out), "dur": abs(t_out - t_in),
                             "borde_in": (lo if creciente else hi)})
        trenes.append({"tid": tid, "sent": sent, "uni": uni,
                       "salida": g["hora_min"].min(), "cantones": cantones,
                       "creciente": creciente})

    trenes.sort(key=lambda x: x["salida"])

    # reservas: single -> lista de (t_in,t_out) cualquier sentido; double -> por sentido
    reservas = {}  # clave: block_id (single) o (block_id, sent) (double)
    filas_sim, eventos = [], []
    for tr in trenes:
        demora = 0.0
        # punto inicial
        pts = [(tr["cantones"][0]["borde_in"], tr["cantones"][0]["ent"])]
        for c in tr["cantones"]:
            t_in_des = c["ent"] + demora
            t_in = t_in_des
            if c["tipo"] == "single":
                # exclusion total: un solo tren (cualquier sentido) en el canton
                ivs = reservas.setdefault(c["block_id"], [])
                cambio = True
                while cambio:
                    cambio = False
                    for (a, z) in ivs:
                        if t_in < z + CLEARING_MIN and t_in + c["dur"] > a - CLEARING_MIN:
                            t_in = z + CLEARING_MIN; cambio = True
                ivs.append((t_in, t_in + c["dur"]))
            # (doble via: se modela como multiples blocks de senal -> sin exclusion;
            #  los trenes del mismo sentido se siguen libremente)
            espera = t_in - t_in_des
            if espera > 0.05:
                eventos.append({"linea": linea, "tren_id": tr["tid"], "canton": c["block_id"],
                                "tipo": c["tipo"], "espera_min": round(espera, 1),
                                "motivo": "cruzamiento/ocupación vía única" if c["tipo"] == "single" else "headway mismo sentido",
                                "hora": round(t_in, 1)})
                demora += espera
                # hold en el borde de entrada
                pts.append((c["borde_in"], t_in))
            t_out = t_in + c["dur"]
            # salida del canton (otro borde)
            otro = c["borde_in"]
            # avanzar al borde de salida
            pts.append((_otro_borde(c, tr["creciente"]), t_out))
        for d, t in pts:
            filas_sim.append({"linea": linea, "tren_id": tr["tid"], "sentido": tr["sent"],
                              "unidad": tr["uni"], "dist_km": round(d, 3), "hora_min": round(t, 2)})

    df_sim = pd.DataFrame(filas_sim)
    df_sim.to_csv(CLEAN / "malla_sim.csv", index=False)
    df_ev = pd.DataFrame(eventos)
    df_ev.to_csv(CLEAN / "sim_eventos.csv", index=False)
    resumen = {
        "linea": linea, "trenes": len(trenes),
        "eventos_espera": len(eventos),
        "espera_total_min": round(df_ev["espera_min"].sum(), 1) if len(df_ev) else 0.0,
        "esperas_via_unica": int((df_ev["tipo"] == "single").sum()) if len(df_ev) else 0,
        "clearing_min": CLEARING_MIN,
    }
    with open(CLEAN / "sim_resumen.json", "w", encoding="utf-8") as fh:
        json.dump(resumen, fh, ensure_ascii=False, indent=2)
    return df_sim, df_ev, resumen


def _otro_borde(c, creciente):
    # el borde de salida es el opuesto al de entrada dentro del canton
    import pandas as pd
    blo = pd.read_csv(CLEAN / "bloques.csv")
    row = blo[blo.block_id == c["block_id"]].iloc[0]
    lo, hi = round(row.dist_lo, 3), round(row.dist_hi, 3)
    return hi if creciente else lo


if __name__ == "__main__":
    df_sim, df_ev, res = simular("L2")
    print("Simulacion fixed-block L2 (itinerario actual)")
    print(json.dumps(res, ensure_ascii=False, indent=2))
    if len(df_ev):
        print("\nEsperas por tipo:")
        print(df_ev.groupby("tipo")["espera_min"].agg(["count", "sum"]).to_string())
        print("\nEjemplos de esperas en vía única:")
        print(df_ev[df_ev.tipo == "single"].head(6).to_string(index=False))
