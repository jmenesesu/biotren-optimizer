"""Etapa 1 — ETL: construye la tabla limpia de horarios (pasajeros + carga).

Ejecuta los extractores de pasajeros y carga y unifica en un unico CSV con
esquema comun. Es la base limpia de la situacion actual.

Salida:
    datos/clean/horarios_limpios.csv
    columnas: fuente, portador, tramo, sentido, tipo_dia, servicio, unidad,
              equipo_vacio, estacion, orden, llegada_min, salida_min, llegada, salida
"""
import sys
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO / "parsers"))
sys.path.append(str(REPO / "etl"))
from config import ITIN_DIR, CLEAN  # noqa: E402
import etl_pasajeros, etl_carga  # noqa: E402

PDF_PAX = ITIN_DIR / "2-410. Itinerario Pasajeros Concepción 30-mar-2026.pdf"
PDF_FEPASA = ITIN_DIR / "2-416. Programa Resto del Año 2026 FEPASA V2.pdf"
PDF_TRANSAP = ITIN_DIR / "2-421. Programa Resto del Año 2026 TRANSAP V2.pdf"


def _hhmm(x):
    if pd.isna(x):
        return ""
    h = int(x // 60) % 24; m = int(round(x % 60))
    if m == 60:
        h = (h + 1) % 24; m = 0
    return f"{h:02d}:{m:02d}"


def construir():
    pax = etl_pasajeros.extraer(PDF_PAX)
    fe = etl_carga.extraer(PDF_FEPASA, "FEPASA")
    tr = etl_carga.extraer(PDF_TRANSAP, "TRANSAP")
    df = pd.concat([pax, fe, tr], ignore_index=True)
    df["llegada"] = df["llegada_min"].map(_hhmm)
    df["salida"] = df["salida_min"].map(_hhmm)
    df.to_csv(CLEAN / "horarios_limpios.csv", index=False)
    return df


if __name__ == "__main__":
    df = construir()
    print(f"TABLA LIMPIA: {len(df)} filas | servicios: {df['servicio'].nunique()}")
    print("\nPor fuente/portador (servicios):")
    print(df.groupby(['fuente', 'portador'])['servicio'].nunique().to_string())
    print("\nColumnas:", list(df.columns))
    print("\nMuestra pasajeros:")
    print(df[df.fuente=='pasajeros'][['portador','tramo','sentido','tipo_dia','servicio','unidad','equipo_vacio','estacion','llegada','salida']].head(4).to_string(index=False))
    print("\nMuestra carga:")
    print(df[df.fuente=='carga'][['portador','servicio','estacion','llegada','salida']].head(4).to_string(index=False))
