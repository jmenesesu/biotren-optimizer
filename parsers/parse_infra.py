"""Parser de infraestructura — formato Metrolinx exportado desde OpenTrack.

Lee 'Export Infraestructure Data (Metrolinx-Format).txt' y produce un CSV
limpio de arcos (edges) con: corredor, línea, vía, longitud, kilometraje de
vértices, señales, velocidades por categoría y sentido, gradiente y radio.

Uso:
    python parsers/parse_infra.py
Salida:
    datos/clean/infra_edges.csv
    datos/clean/infra_resumen_corredores.csv
"""
import csv
import pandas as pd
from config import INFRA_DIR, CLEAN

ARCHIVO = INFRA_DIR / "Export Infraestructure Data (Metrolinx-Format).txt"

COLS = [
    "document", "line", "track", "edge_name", "edge_id", "edge_length_m",
    "v1_id", "v2_id", "v1_name", "v2_name", "v1_km", "v2_km",
    "v1_sig", "v2_sig", "v1_switch_time", "v2_switch_time",
    "v1_stat_id", "v2_stat_id",
    "speed_1_1", "speed_1_2", "speed_1_3", "speed_1_4",
    "speed_2_1", "speed_2_2", "speed_2_3", "speed_2_4",
    "gradient_permil", "curve_radius_m",
]
NUM_COLS = [
    "edge_length_m", "v1_km", "v2_km",
    "speed_1_1", "speed_1_2", "speed_1_3", "speed_1_4",
    "speed_2_1", "speed_2_2", "speed_2_3", "speed_2_4",
    "gradient_permil", "curve_radius_m",
]


def _to_num(x):
    x = (x or "").strip()
    if x == "":
        return None
    return float(x.replace(",", "."))


def parse():
    with open(ARCHIVO, encoding="latin-1") as f:
        lines = f.readlines()

    # Saltar comentarios (//) y localizar la cabecera real
    data_rows = []
    for ln in lines:
        if ln.startswith("//") or not ln.strip():
            continue
        if ln.startswith("Document Name"):  # cabecera sin //
            continue
        data_rows.append(ln.rstrip("\n"))

    rows = []
    for ln in data_rows:
        parts = ln.split("\t")
        # Completar a la cantidad de columnas esperada
        parts += [""] * (len(COLS) - len(parts))
        rec = dict(zip(COLS, parts[: len(COLS)]))
        for c in NUM_COLS:
            rec[c] = _to_num(rec[c])
        rows.append(rec)

    df = pd.DataFrame(rows, columns=COLS)
    # Velocidad máxima de referencia del arco (máx de los perfiles definidos)
    speed_cols = [c for c in df.columns if c.startswith("speed_")]
    df["vmax_kmh"] = df[speed_cols].max(axis=1)
    df.to_csv(CLEAN / "infra_edges.csv", index=False, quoting=csv.QUOTE_MINIMAL)

    # Resumen por corredor
    resumen = (
        df.groupby("document")
        .agg(
            arcos=("edge_id", "count"),
            largo_total_m=("edge_length_m", "sum"),
            vmax_kmh=("vmax_kmh", "max"),
            gradiente_min=("gradient_permil", "min"),
            gradiente_max=("gradient_permil", "max"),
        )
        .reset_index()
    )
    resumen.to_csv(CLEAN / "infra_resumen_corredores.csv", index=False)
    return df, resumen


if __name__ == "__main__":
    df, resumen = parse()
    print(f"Arcos parseados: {len(df)}")
    print(f"Largo total de la red (km): {df['edge_length_m'].sum()/1000:.2f}")
    print("\nResumen por corredor:")
    print(resumen.to_string(index=False))
    print(f"\nGuardado en: {CLEAN}")
