"""Tramos de via unica y deteccion de cruzamientos no permitidos.

Sobre el eje espacial de cada linea (ejes_distancia), define los tramos de via
unica y detecta cuando dos trenes de sentido opuesto ocupan el MISMO tramo en
ventanas de tiempo que se solapan (se topan sin poder cruzarse) -> conflicto.

Los tramos con desvios intermedios (Hualqui-Laja) se marcan como informativos
(permiten cruce en desvios) y no se auto-marcan como conflicto.

Salida:
    datos/clean/via_unica.csv   (linea, nombre, dist_lo, dist_hi, bloquea)
    datos/clean/conflictos.csv  (linea, segmento, tren_a, unidad_a, tren_b, unidad_b,
                                 dist_mid, hora_mid)
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO / "parsers"))
from config import CLEAN  # noqa: E402

# Tramos de via unica por linea, en distancia (km) del eje espacial.
# bloquea=True: bloque sin desvios intermedios -> cruce solo en extremos (se
# detectan conflictos). bloquea=False: con desvios -> informativo.
VIA_UNICA = {
    "L2": [("Concepción–salida Túnel Chepe", 1.0, 3.0, True)],
    "L1": [("Mercado–El Arenal", 82.79, 84.78, True),
           ("Hualqui–La Leonera", 46.92, 55.32, True),
           ("Hualqui–Laja (con desvíos)", 1.60, 46.92, False)],
}


def _ocupacion(g, lo, hi):
    """Ventana [t_in, t_out] (min) en que el tren g ocupa el tramo [lo,hi]."""
    d = g["dist_km"].to_numpy()
    t = g["hora_min"].to_numpy()
    if d.max() < lo - 1e-6 or d.min() > hi + 1e-6:
        return None
    order = np.argsort(d)
    ds, ts = d[order], t[order]
    a = max(lo, ds.min())
    b = min(hi, ds.max())
    t_a = float(np.interp(a, ds, ts))
    t_b = float(np.interp(b, ds, ts))
    return (min(t_a, t_b), max(t_a, t_b))


def conflictos():
    malla = pd.read_csv(CLEAN / "malla_real.csv")
    filas_vu, filas_cf = [], []
    for linea, tramos in VIA_UNICA.items():
        m = malla[malla.linea == linea]
        if m.empty:
            continue
        for nombre, lo, hi, bloquea in tramos:
            filas_vu.append({"linea": linea, "nombre": nombre,
                             "dist_lo": lo, "dist_hi": hi, "bloquea": bloquea})
            if not bloquea:
                continue
            # ocupaciones por tren con su sentido
            ocup = []
            for tid, g in m.groupby("tren_id"):
                win = _ocupacion(g, lo, hi)
                if win:
                    ocup.append((tid, g["sentido"].iloc[0],
                                 g["unidad"].iloc[0] if "unidad" in g else "", win))
            # pares de sentido opuesto con solape temporal
            for i in range(len(ocup)):
                for j in range(i + 1, len(ocup)):
                    a, b = ocup[i], ocup[j]
                    if a[1] == b[1]:
                        continue  # mismo sentido
                    s = max(a[3][0], b[3][0]); e = min(a[3][1], b[3][1])
                    if s < e:  # solape -> conflicto
                        filas_cf.append({
                            "linea": linea, "segmento": nombre,
                            "tren_a": a[0], "unidad_a": a[2],
                            "tren_b": b[0], "unidad_b": b[2],
                            "dist_mid": round((lo + hi) / 2, 2),
                            "hora_mid": round((s + e) / 2, 1)})
    pd.DataFrame(filas_vu).to_csv(CLEAN / "via_unica.csv", index=False)
    df = pd.DataFrame(filas_cf)
    df.to_csv(CLEAN / "conflictos.csv", index=False)
    return df, pd.DataFrame(filas_vu)


if __name__ == "__main__":
    df, vu = conflictos()
    print("Tramos de via unica:")
    print(vu.to_string(index=False))
    print(f"\nConflictos detectados (cruce en via unica sin desvio): {len(df)}")
    if len(df):
        print(df.groupby(["linea", "segmento"]).size().to_string())
        print("\nEjemplos:")
        print(df.head(8).to_string(index=False))
