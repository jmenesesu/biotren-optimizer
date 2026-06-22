"""Generador de la malla del dia completo para el diagrama de Marey (L1 y L2).

Para cada linea genera, a lo largo del dia (segun la frecuencia optima de cada
franja), los trenes de ambos sentidos sobre un UNICO eje espacial (distancia
acumulada desde el origen). Asi ambos sentidos comparten el eje y sus cruces
representan cruzamientos reales.

Salida:
    datos/clean/malla_marey.csv  (linea, tren_id, sentido, estacion, dist_km, hora_min)
"""
import sys
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO / "parsers"))
from config import CLEAN  # noqa: E402
from ejes_distancia import eje_L1, eje_L2  # noqa: E402

# Ventanas horarias del dia (min desde 00:00) y la franja de demanda asociada
VENTANAS = [(300, 600, "05-10"), (600, 960, "10-16"), (960, 1440, "16-24")]

# Sentido "creciente en distancia" por linea (desde el origen del eje)
# L2: CC->CW (Concepcion 0 -> Coronel). L1: TH->LJ (Mercado 0 -> Laja).
SENTIDO_ITIN = {
    "L2": {"crece": "CC->CW", "decrece": "CW->CC"},
    "L1": {"crece": "TH->LJ", "decrece": "LJ->TH"},
}


def _tviaje_map(itin, tramo, sentido):
    sub = itin[(itin.tramo == tramo) & (itin.sentido == sentido)]
    return dict(zip(sub["estacion"], sub["t_viaje_s"].fillna(0)))


def _intervalo(fr_df, linea, franja):
    row = fr_df[(fr_df.linea == linea) & (fr_df.franja == franja)]
    if len(row) and pd.notna(row["intervalo_min"].iloc[0]):
        return float(row["intervalo_min"].iloc[0])
    return None


def _genera_linea(linea, eje, itin, fr_df, filas):
    estaciones = list(eje["estacion"])
    distkm = dict(zip(eje["estacion"], eje["dist_km"]))
    itn = SENTIDO_ITIN[linea]
    for sentido_key, orden in [("crece", estaciones), ("decrece", list(reversed(estaciones)))]:
        sent_itin = itn[sentido_key]
        tvi = _tviaje_map(itin, linea, sent_itin)
        # tiempo acumulado a lo largo del recorrido (origen = primera de 'orden')
        cum = [0.0]
        for s in orden[1:]:
            cum.append(cum[-1] + tvi.get(s, 60) / 60.0)
        # generar salidas por franja
        tren = 0
        for ini, fin, franja in VENTANAS:
            interv = _intervalo(fr_df, linea, franja)
            if not interv:
                continue
            t0 = ini
            while t0 < fin:
                tren += 1
                tid = f"{linea}-{sent_itin}-{tren}"
                for s, c in zip(orden, cum):
                    filas.append({
                        "linea": linea, "tren_id": tid, "sentido": sent_itin,
                        "estacion": s, "dist_km": round(distkm[s], 3),
                        "hora_min": round(t0 + c, 2),
                    })
                t0 += interv


def generar():
    itin = pd.read_csv(CLEAN / "itinerario_tiempos.csv")
    fr_df = pd.read_csv(CLEAN / "optim_frecuencias.csv")
    filas = []
    _genera_linea("L2", eje_L2(), itin, fr_df, filas)
    _genera_linea("L1", eje_L1(), itin, fr_df, filas)
    df = pd.DataFrame(filas)
    df.to_csv(CLEAN / "malla_marey.csv", index=False)
    return df


if __name__ == "__main__":
    df = generar()
    for linea in ["L2", "L1"]:
        g = df[df.linea == linea]
        print(f"{linea}: {g['tren_id'].nunique()} trenes/dia, "
              f"{g['estacion'].nunique()} estaciones, "
              f"dist 0..{g['dist_km'].max():.1f} km, "
              f"hora {g['hora_min'].min():.0f}..{g['hora_min'].max():.0f} min")
    print(f"\nFilas: {len(df)} | Guardado: {CLEAN/'malla_marey.csv'}")
