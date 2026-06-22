"""Calibracion del motor de tiempos contra el itinerario vigente.

El motor entrega el tiempo tecnico minimo corriendo hasta la velocidad limite
de via. El horario comercial es mayor: la operacion no corre a la velocidad de
via entre paradas cercanas y el itinerario incorpora margenes de recuperacion.

Este modulo estima dos cosas a partir de la comparacion motor vs itinerario:

  1) factor_velocidad_comercial: factor (<1) aplicado a la velocidad limite que
     mejor reproduce los tiempos del itinerario (interpretacion fisica: la
     velocidad comercial es una fraccion de la velocidad de via).
  2) suplemento: margen residual (horario / tecnico - 1) una vez fijada la
     velocidad comercial.

Escribe datos/clean/calibracion.json para que la optimizacion use tiempos
consistentes con el horario.

Uso:
    python motor/calibrar.py
"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1] / "parsers"))
from config import CLEAN  # noqa: E402
from running_time import tiempo_recorrido, construir_vehiculo_desde_csv, SubTramo  # noqa: E402
from corridor_builder import construir_linea, subtramos_entre  # noqa: E402


def _escala_subs(subs, factor):
    return [SubTramo(s.largo_m, s.vlim_kmh * factor, s.gradiente_permil) for s in subs]


def tiempos_por_tramo(perfil, est, veh, factor=1.0):
    out = []
    km_prev = 0.0
    for _, row in est.iterrows():
        subs = _escala_subs(subtramos_entre(perfil, km_prev, row["km"]), factor)
        t, _, _ = tiempo_recorrido(subs, veh)
        out.append((row["estacion"], row["t_viaje_s"], t))
        km_prev = row["km"]
    return out


def calibrar(linea="L2", sentido="CC->CW"):
    dv = pd.read_csv(CLEAN / "material_rodante.csv")
    dc = pd.read_csv(CLEAN / "esfuerzo_tractor.csv")
    veh = construir_vehiculo_desde_csv("SFE-100 normal", dv, dc)
    perfil, est = construir_linea(linea, sentido)

    # Buscar el factor de velocidad comercial que minimiza el error medio absoluto
    factores = np.arange(0.45, 1.01, 0.025)
    mejor = None
    for f in factores:
        tt = tiempos_por_tramo(perfil, est, veh, f)
        t_tec = sum(x[2] for x in tt)
        t_itin = sum(x[1] for x in tt)
        err = abs(t_tec - t_itin) / t_itin
        if mejor is None or err < mejor[1]:
            mejor = (f, err, t_tec, t_itin)
    factor, err, t_tec, t_itin = mejor
    suplemento = t_itin / t_tec - 1.0

    cal = {
        "linea": linea, "sentido": sentido,
        "vehiculo_ref": veh.nombre,
        "factor_velocidad_comercial": round(float(factor), 3),
        "tiempo_tecnico_min": round(t_tec / 60, 2),
        "tiempo_itinerario_min": round(t_itin / 60, 2),
        "suplemento_residual": round(float(suplemento), 3),
        "error_medio_abs": round(float(err), 4),
        "nota": ("Tiempo comercial = motor(velocidad_via * factor). "
                 "Suplemento residual aplicable sobre el tiempo tecnico calibrado. "
                 "Coeficientes Davis y deceleracion del motor son supuestos; "
                 "recalibrar con mediciones reales o contra OpenTrack."),
    }
    with open(CLEAN / "calibracion.json", "w", encoding="utf-8") as fh:
        json.dump(cal, fh, ensure_ascii=False, indent=2)
    return cal, factor, est, perfil, veh


if __name__ == "__main__":
    cal, factor, est, perfil, veh = calibrar()
    print("Calibracion del motor contra el itinerario (L2 CC->CW)")
    print("=" * 60)
    print(f"Factor de velocidad comercial: {cal['factor_velocidad_comercial']} "
          f"(velocidad comercial = {cal['factor_velocidad_comercial']*100:.0f}% de la de via)")
    print(f"Tiempo tecnico calibrado: {cal['tiempo_tecnico_min']} min")
    print(f"Tiempo itinerario:        {cal['tiempo_itinerario_min']} min")
    print(f"Suplemento residual:      {cal['suplemento_residual']*100:.1f}%")
    print(f"Error medio absoluto:     {cal['error_medio_abs']*100:.1f}%")

    # tabla por tramo con el factor calibrado
    print("\nTiempos por tramo con factor calibrado:")
    print(f"{'-> estacion':<28}{'t itin':>8}{'t motor':>9}{'dif %':>8}")
    for est_n, t_i, t_m in tiempos_por_tramo(perfil, est, veh, factor):
        dif = (t_m - t_i) / t_i * 100
        print(f"{est_n:<28}{t_i/60:8.2f}{t_m/60:9.2f}{dif:+8.1f}")
    print(f"\nGuardado: {CLEAN/'calibracion.json'}")
