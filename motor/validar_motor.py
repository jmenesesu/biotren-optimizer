"""Validación del motor de tiempos contra el itinerario vigente.

Usa el PERFIL REAL de vía (velocidad límite y gradiente por kilómetro, de la
infraestructura) construido por corridor_builder, en lugar de un perfil
uniforme. Compara, tramo a tramo, el tiempo de recorrido del motor con el
tiempo de viaje del itinerario para L2 (Concepción–Coronel).

Uso:
    python motor/validar_motor.py
"""
import sys
from pathlib import Path
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1] / "parsers"))
from config import CLEAN  # noqa: E402
from running_time import tiempo_recorrido, construir_vehiculo_desde_csv  # noqa: E402
from corridor_builder import construir_linea, subtramos_entre  # noqa: E402


def main():
    df_veh = pd.read_csv(CLEAN / "material_rodante.csv")
    df_curva = pd.read_csv(CLEAN / "esfuerzo_tractor.csv")

    veh = construir_vehiculo_desde_csv("SFE-100 normal", df_veh, df_curva)
    print(f"Vehículo: {veh.nombre} | masa {veh.masa_t} t | vmax {veh.vmax_kmh} km/h")
    print(f"Deceleración servicio: {veh.dec_servicio} m/s²  (supuesto, calibrable)\n")

    perfil, est = construir_linea("L2", "CC->CW")
    print("Validación L2 Concepción->Coronel con perfil real de vía")
    print("=" * 64)

    km_prev = 0.0
    t_itin_total = 0.0
    t_motor_total = 0.0
    print(f"{'Tramo (->estación)':<28}{'dist km':>8}{'t itin':>8}{'t motor':>9}{'dif %':>8}")
    for _, row in est.iterrows():
        km = row["km"]
        t_itin = row["t_viaje_s"]
        subs = subtramos_entre(perfil, km_prev, km)
        t_motor, _, _ = tiempo_recorrido(subs, veh)
        dif = (t_motor - t_itin) / t_itin * 100 if t_itin else 0
        print(f"{row['estacion']:<28}{km-km_prev:8.2f}{t_itin/60:8.2f}"
              f"{t_motor/60:9.2f}{dif:+8.1f}")
        t_itin_total += t_itin
        t_motor_total += t_motor
        km_prev = km

    print("=" * 64)
    dif_t = (t_motor_total - t_itin_total) / t_itin_total * 100
    print(f"{'TOTAL':<28}{km_prev:8.2f}{t_itin_total/60:8.2f}"
          f"{t_motor_total/60:9.2f}{dif_t:+8.1f}")
    print(f"\nTiempo de viaje itinerario: {t_itin_total/60:.2f} min")
    print(f"Tiempo de viaje motor (perfil real): {t_motor_total/60:.2f} min")
    print(f"Diferencia global: {dif_t:+.1f}%")
    print("\nLectura: el itinerario incorpora márgenes comerciales y de recuperación")
    print("sobre el tiempo técnico. Un motor que entrega tiempos algo menores al")
    print("itinerario es el comportamiento esperado; el margen medio observado es")
    print("un insumo para fijar el suplemento de tiempo en la optimización.")


if __name__ == "__main__":
    main()
