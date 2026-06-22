"""Cantones (blocks) de via para la simulacion fixed-block.

Los limites de cada canton se toman de las SEÑALES PRINCIPALES reales de OpenTrack
(Metrolinx), que son las que delimitan un block en señalizacion fixed-block. Se
añaden ademas las estaciones (para etiquetar y como stops) y los bordes de los
tramos de via unica. Solo se usan señales dentro del rango del eje de pasajeros
de cada linea.
  - tipo 'single': via unica -> capacidad 1 tren, ambos sentidos.
  - tipo 'double': doble via -> 1 tren por sentido.

Si una zona no tiene señales en OpenTrack, el canton queda definido solo por
estaciones/bordes (se declara en la columna 'limite' = 'estacion').

Salida:
    datos/clean/bloques.csv (linea, block_id, dist_lo, dist_hi, longitud_m, tipo,
                             limite, nombre)
"""
import sys
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO / "parsers"))
sys.path.append(str(REPO / "optimizador"))
from config import CLEAN  # noqa: E402
from ejes_distancia import eje_L1, eje_L2  # noqa: E402
from via_unica import VIA_UNICA  # noqa: E402
import estaciones_maestro as em  # noqa: E402


def _bloques_linea(linea, eje):
    est = eje.sort_values("dist_km").reset_index(drop=True)
    km_min, km_max = est["dist_km"].min(), est["dist_km"].max()
    est_km = set(round(d, 3) for d in est["dist_km"])
    sig_km = set(round(k, 3) for k in em.senales_principales_km(linea)
                 if km_min - 0.1 <= k <= km_max + 0.1)
    vu_km = set()
    for nombre, lo, hi, bloquea in VIA_UNICA.get(linea, []):
        vu_km.add(round(lo, 3)); vu_km.add(round(hi, 3))
    limites = sorted(est_km | sig_km | vu_km)
    nombre_de = {round(r.dist_km, 3): r.estacion for _, r in est.iterrows()}
    filas = []
    for i in range(len(limites) - 1):
        lo, hi = limites[i], limites[i + 1]
        if hi - lo < 1e-3:
            continue
        mid = (lo + hi) / 2
        tipo = "double"
        for _, vlo, vhi, bloquea in VIA_UNICA.get(linea, []):
            if vlo - 1e-6 <= mid <= vhi + 1e-6 and bloquea:
                tipo = "single"
        lim_lo = "señal" if lo in sig_km and lo not in est_km else "estacion"
        a = nombre_de.get(lo, f"km{lo:.2f}")
        b = nombre_de.get(hi, f"km{hi:.2f}")
        filas.append({"linea": linea, "block_id": f"{linea}-B{i}",
                      "dist_lo": lo, "dist_hi": hi,
                      "longitud_m": round(abs(hi - lo) * 1000, 0),
                      "tipo": tipo, "limite": lim_lo, "nombre": f"{a} → {b}"})
    return filas


def construir():
    filas = _bloques_linea("L2", eje_L2()) + _bloques_linea("L1", eje_L1())
    df = pd.DataFrame(filas)
    df.to_csv(CLEAN / "bloques.csv", index=False)
    return df


if __name__ == "__main__":
    df = construir()
    for linea in ["L2", "L1"]:
        g = df[df.linea == linea]
        ns = em.senales_principales_km(linea)
        print(f"{linea}: {len(g)} cantones ({(g.tipo=='single').sum()} en vía única); "
              f"{len(ns)} señales principales en la línea")
