"""Parser de material rodante — railML 2.2 exportado desde OpenTrack.

Extrae los vehículos motores (engines) con masa, potencia, factor de masa
rotante y velocidad máxima, más sus curvas de esfuerzo tractor (esfuerzo vs
velocidad). Cuando un vehículo tiene varias propulsiones, se prefiere la de
descripción 'DC 3000V' (modo de operación real de la catenaria de Biotren).

Uso:
    python parsers/parse_rolling_stock.py
Salida:
    datos/clean/material_rodante.csv          (una fila por vehículo)
    datos/clean/esfuerzo_tractor.csv          (curva v[km/h] -> F[N] por vehículo)
"""
from lxml import etree
import pandas as pd
from config import RS_DIR, CLEAN

ARCHIVO = RS_DIR / "Export Rolling Stock (railML-Format) - Version 2.2.railml"
NS = {"r": "http://www.railml.org/schemas/2013"}

# Vehículos de interés operacional para Biotren (motores de pasajeros)
FLOTA_BIOTREN = ["SFE-100", "SFE-200", "SFE-100/200", "UT-440", "UT-CM"]


def _pick_propulsion(engine):
    """Devuelve la propulsión de operación (prefiere DC 3000V)."""
    props = engine.findall("r:propulsion", NS)
    if not props:
        return None
    for p in props:
        if "3000" in (p.get("description") or ""):
            return p
    return props[0]


def parse():
    tree = etree.parse(str(ARCHIVO))
    root = tree.getroot()

    veh_rows = []
    curve_rows = []
    for v in root.findall(".//r:vehicle", NS):
        eng = v.find("r:engine", NS)
        if eng is None:
            continue  # es un trailer (remolque), no motor
        prop = _pick_propulsion(eng)
        vid = v.get("id")
        name = v.get("name")
        veh_rows.append({
            "vehicle_id": vid,
            "nombre": name,
            "largo_m": float(v.get("length") or 0),
            "vmax_kmh": float(v.get("speed") or 0),
            "masa_bruta_t": float(v.get("bruttoWeight") or 0),
            "masa_adherente_t": float(v.get("bruttoAdhesionWeight") or 0),
            "potencia_w": float(prop.get("power") or 0) if prop is not None else None,
            "factor_masa_rotante": float(prop.get("rotationMassFactor") or 1.0) if prop is not None else 1.0,
            "modo_propulsion": (prop.get("description") if prop is not None else None),
        })
        if prop is not None:
            te = prop.find("r:tractiveEffort", NS)
            if te is not None:
                for vl in te.findall(".//r:valueLine", NS):
                    x = vl.get("xValue")
                    val = vl.find("r:values", NS)
                    y = val.get("yValue") if val is not None else None
                    if x is not None and y is not None:
                        curve_rows.append({
                            "vehicle_id": vid, "nombre": name,
                            "velocidad_kmh": float(x), "esfuerzo_n": float(y),
                        })

    df_v = pd.DataFrame(veh_rows)
    df_c = pd.DataFrame(curve_rows)

    # Marca de pertenencia a la flota Biotren
    def es_biotren(n):
        return any(k in (n or "") for k in FLOTA_BIOTREN)
    df_v["flota_biotren"] = df_v["nombre"].map(es_biotren)

    df_v.to_csv(CLEAN / "material_rodante.csv", index=False)
    df_c.to_csv(CLEAN / "esfuerzo_tractor.csv", index=False)
    return df_v, df_c


if __name__ == "__main__":
    df_v, df_c = parse()
    print(f"Vehículos motores: {len(df_v)}  (Biotren: {df_v['flota_biotren'].sum()})")
    print("\nFlota Biotren detectada:")
    cols = ["nombre", "masa_bruta_t", "vmax_kmh", "potencia_w", "modo_propulsion"]
    print(df_v[df_v["flota_biotren"]][cols].to_string(index=False))
    print(f"\nPuntos de curva de esfuerzo tractor: {len(df_c)}")
    print(f"Guardado en: {CLEAN}")
