"""Parser del itinerario de pasajeros (PDF 2-410).

Extrae, por tramo y sentido, los tiempos de viaje entre estaciones consecutivas
(columnas 'Tiempo de Viaje' y 'Tiempo de Viaje Ext.') y los tiempos de detención.
Estos tiempos son el patrón de referencia para validar el motor de tiempos.

También extrae la lista de números de servicio detectados.

Uso:
    python parsers/parse_itinerary.py
Salida:
    datos/clean/itinerario_tiempos.csv   (tramo, sentido, estacion, t_viaje_s, t_viaje_ext_s, detencion_s)
    datos/clean/servicios.csv            (numero de servicio)
"""
import re
import subprocess
import pandas as pd
from config import ITIN_DIR, CLEAN

PDF = ITIN_DIR / "2-410. Itinerario Pasajeros Concepción 30-mar-2026.pdf"

# Encabezados de sección y la dirección que representan
SECCIONES = [
    ("Concepción a Coronel", "L2", "CC->CW"),
    ("Coronel a Concepción", "L2", "CW->CC"),
    ("Laja a Talcahuano", "L1", "LJ->TH"),
    ("Talcahuano a Laja", "L1", "TH->LJ"),
]

TIME_RE = re.compile(r"^(\d{1,2}:\d{2}:\d{2})")
# Línea de estación: nombre (letras/espacios/puntos) seguido de >=1 tiempos H:MM:SS
ROW_RE = re.compile(
    r"^\s*([A-Za-zÁÉÍÓÚÑáéíóúñ\.\(\)\- ]+?)\s+"
    r"(\d{1,2}:\d{2}:\d{2})"            # tiempo de viaje
    r"(?:\s+(\d{1,2}:\d{2}:\d{2}))?"    # tiempo de viaje ext (opcional)
    r"(?:\s+(\d{2}:\d{2}))?"            # detención mm:ss (opcional)
)


def _hms_to_s(t):
    if not t:
        return None
    p = [int(x) for x in t.split(":")]
    if len(p) == 3:
        return p[0] * 3600 + p[1] * 60 + p[2]
    if len(p) == 2:
        return p[0] * 60 + p[1]
    return None


def parse():
    txt = subprocess.run(
        ["pdftotext", "-layout", str(PDF), "-"],
        capture_output=True, text=True, encoding="utf-8"
    ).stdout
    lines = txt.splitlines()

    seccion_actual = None
    registros = []
    vistos = set()
    servicios = set()

    for ln in lines:
        # ¿es un encabezado de sección?
        for clave, linea, sentido in SECCIONES:
            if clave in ln:
                seccion_actual = (linea, sentido)
                break
        # números de servicio (5 dígitos que empiezan con 20)
        for m in re.findall(r"\b(20\d{3})\b", ln):
            servicios.add(m)
        # ¿es una fila de estación con tiempos?
        if seccion_actual:
            m = ROW_RE.match(ln)
            if m:
                est = re.sub(r"\s+", " ", m.group(1)).strip()
                # filtrar falsos positivos (etiquetas no-estación)
                if len(est) < 3 or est.lower() in ("tren", "rotación", "detención"):
                    continue
                key = (seccion_actual[0], seccion_actual[1], est)
                if key in vistos:
                    continue
                vistos.add(key)
                registros.append({
                    "tramo": seccion_actual[0],
                    "sentido": seccion_actual[1],
                    "estacion": est,
                    "t_viaje_s": _hms_to_s(m.group(2)),
                    "t_viaje_ext_s": _hms_to_s(m.group(3)),
                    "detencion_s": _hms_to_s(m.group(4)),
                })

    df = pd.DataFrame(registros)
    df.to_csv(CLEAN / "itinerario_tiempos.csv", index=False)

    df_serv = pd.DataFrame(sorted(servicios), columns=["servicio"])
    df_serv.to_csv(CLEAN / "servicios.csv", index=False)
    return df, df_serv


if __name__ == "__main__":
    df, df_serv = parse()
    print(f"Filas de tiempos por estación: {len(df)}")
    print(f"Servicios distintos detectados: {len(df_serv)}")
    for (tramo, sentido), g in df.groupby(["tramo", "sentido"]):
        tot = g["t_viaje_s"].sum()
        print(f"  {tramo} {sentido}: {len(g)} estaciones, "
              f"tiempo de viaje acumulado {tot/60:.1f} min")
    print(f"\nEjemplo (L2 CC->CW):")
    ej = df[(df.tramo == 'L2') & (df.sentido == 'CC->CW')][['estacion', 't_viaje_s', 'detencion_s']]
    print(ej.to_string(index=False))
    print(f"\nGuardado en: {CLEAN}")
