"""Trenes dobles (acoplados), leídos del gráfico de rotaciones del itinerario.

En el gráfico, [A] = Acople y [D] = Desacople. Cuando dos automotores se acoplan,
corren un tramo como UN tren doble (doble capacidad) y luego se desacoplan. Esto
también explica el reposicionamiento de la segunda unidad (no "aparece" sola en el
otro extremo: viaja acoplada).

Confirmado (Lun-Vie):
  - Servicio 20281 (CC->CW, 5:30 Concepción->Coronel, EQUIPO VACÍO): SFE 3 + SFE 5
    se acoplan en Concepción y se desacoplan en Coronel.

NOTA: la extracción completa de todos los acoples del día requiere leer el gráfico
de rotaciones (texto vectorial CAD) tramo por tramo; aquí se codifican los
confirmados y el archivo es extensible.

Salida: datos/clean/trenes_dobles.csv
"""
import sys
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO / "parsers"))
from config import CLEAN  # noqa: E402

# servicio, sentido, tipo_dia, unidad_titular (la que tiene el servicio en horarios),
# unidad_acoplada (la segunda), donde acopla y desacopla.
DOBLES = [
    {"servicio": "20281", "sentido": "CC->CW", "tipo_dia": "Lun-Vie",
     "unidad_a": "SFE 3", "unidad_b": "SFE 5",
     "acople": "CONCEPCIÓN", "desacople": "CORONEL", "equipo_vacio": True},
]


def construir():
    df = pd.DataFrame(DOBLES)
    df.to_csv(CLEAN / "trenes_dobles.csv", index=False)
    return df


if __name__ == "__main__":
    df = construir()
    print(f"Trenes dobles (confirmados): {len(df)}")
    print(df.to_string(index=False))
