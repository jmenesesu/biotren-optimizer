"""Ejecuta todos los parsers y la validacion/calibracion del motor en orden.

Uso:
    python run_all.py
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
PASOS = [
    ("Infraestructura", "parsers/parse_infra.py"),
    ("Material rodante", "parsers/parse_rolling_stock.py"),
    ("Matrices OD / perfil", "parsers/parse_od.py"),
    ("Itinerario", "parsers/parse_itinerary.py"),
    ("Trenes de carga", "parsers/parse_freight.py"),
    ("Geo estaciones (KML)", "parsers/parse_geo.py"),
    ("Red topologia (OTML)", "parsers/parse_red_topologia.py"),
    ("Salidas reales (itinerario)", "parsers/parse_itinerario_real.py"),
    ("Validacion del motor (perfil real)", "motor/validar_motor.py"),
    ("Calibracion del motor", "motor/calibrar.py"),
    ("Optimizador de capacidad", "optimizador/optimizar_capacidad.py"),
    ("Generar malla optima (Marey)", "optimizador/generar_malla.py"),
    ("Generar malla real (Marey)", "optimizador/generar_malla_real.py"),
    ("Via unica y conflictos", "optimizador/via_unica.py"),
]


def main():
    for nombre, script in PASOS:
        print(f"\n{'='*60}\n>>> {nombre}  ({script})\n{'='*60}")
        r = subprocess.run([sys.executable, script], cwd=REPO)
        if r.returncode != 0:
            print(f"FALLO en {script}")
            sys.exit(r.returncode)
    print("\nTodos los pasos completados. Datasets limpios en datos/clean/.")


if __name__ == "__main__":
    main()
