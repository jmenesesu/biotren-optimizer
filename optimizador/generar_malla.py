"""Generador de la malla (insumo del diagrama de Marey).

Construye una tabla tiempo-distancia de los trenes de L2 (Concepcion-Coronel)
combinando:
  - posicion kilometrica real de cada estacion (corridor_builder),
  - tiempos de viaje entre estaciones del itinerario,
  - la frecuencia optima por franja del optimizador (intervalo).

Cada tren es una secuencia de puntos (tiempo, km). Al graficar km vs tiempo se
obtiene el diagrama de Marey: cada linea diagonal es un tren; el cruce de lineas
de sentidos opuestos indica un cruzamiento.

Uso:
    python optimizador/generar_malla.py
Salida:
    datos/clean/malla_marey.csv  (tren_id, linea, sentido, estacion, km, t_min)
"""
import sys
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO / "parsers"))
sys.path.append(str(REPO / "motor"))
from config import CLEAN  # noqa: E402
from corridor_builder import construir_linea  # noqa: E402

# Ventana a graficar (minutos desde el inicio) y franja de referencia
VENTANA_MIN = 120         # 2 horas
FRANJA_REF = "05-10"      # punta manana


def _secuencia_estaciones(sentido):
    """Lista [(estacion, km, t_viaje_s)] incluyendo Concepcion como origen."""
    perfil, est = construir_linea("L2", "CC->CW")
    filas = [("CONCEPCIÓN", 0.0, 0)]
    for _, r in est.iterrows():
        filas.append((r["estacion"], float(r["km"]), int(r["t_viaje_s"])))
    if sentido == "CW->CC":
        # invertir: recorrido desde Coronel (km max) hacia Concepcion
        km_max = filas[-1][1]
        inv = []
        # tiempos de viaje del sentido CW->CC desde el itinerario
        it = pd.read_csv(CLEAN / "itinerario_tiempos.csv")
        cw = it[(it.tramo == "L2") & (it.sentido == "CW->CC")].reset_index(drop=True)
        # construir secuencia inversa de estaciones con km espejados
        ests_rev = list(reversed(filas))
        # mapear tiempos de viaje CW->CC por orden
        tvs = [0] + list(cw["t_viaje_s"]) if len(cw) else [f[2] for f in reversed(filas)]
        for i, (e, km, _) in enumerate(ests_rev):
            tv = tvs[i] if i < len(tvs) else 0
            inv.append((e, km_max - km, int(tv)))
        return inv
    return filas


def generar():
    fr = pd.read_csv(CLEAN / "optim_frecuencias.csv")
    filas_out = []
    for sentido in ["CC->CW", "CW->CC"]:
        seq = _secuencia_estaciones(sentido)
        # intervalo optimo de la franja de referencia para L2
        row = fr[(fr.linea == "L2") & (fr.franja == FRANJA_REF)]
        intervalo = float(row["intervalo_min"].iloc[0]) if len(row) and pd.notna(row["intervalo_min"].iloc[0]) else 15.0
        # tiempos acumulados a lo largo del recorrido
        t_acum = []
        acc = 0.0
        for i, (e, km, tv) in enumerate(seq):
            acc += tv / 60.0
            t_acum.append(acc if i > 0 else 0.0)
        # generar salidas cada 'intervalo' minutos dentro de la ventana
        salida = 0.0
        tren = 0
        while salida <= VENTANA_MIN:
            tren += 1
            tid = f"L2-{sentido}-{tren}"
            for (e, km, tv), ta in zip(seq, t_acum):
                filas_out.append({
                    "tren_id": tid, "linea": "L2", "sentido": sentido,
                    "estacion": e, "km": round(km, 3), "t_min": round(salida + ta, 2),
                })
            salida += intervalo
    df = pd.DataFrame(filas_out)
    df.to_csv(CLEAN / "malla_marey.csv", index=False)
    return df


if __name__ == "__main__":
    df = generar()
    print("Malla generada (diagrama de Marey, L2)")
    print(f"Filas: {len(df)} | trenes: {df['tren_id'].nunique()} "
          f"| ventana: {VENTANA_MIN} min | franja: {FRANJA_REF}")
    print(df.head(16).to_string(index=False))
    print(f"\nGuardado: {CLEAN/'malla_marey.csv'}")
