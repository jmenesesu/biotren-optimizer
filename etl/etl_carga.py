"""ETL itinerario de CARGA (FEPASA 2-416, TRANSAP 2-421) -> tabla limpia.

Cada pagina es una tabla: km (izq), distancia parcial, estacion (centro) y, por
cada tren (columna del encabezado), sub-columnas Llega/Sale. Se extraen solo las
filas con kilometraje (descarta notas al pie y referencias de cruce).

Devuelve un DataFrame con esquema comun (fuente='carga').
"""
import re
import pandas as pd
import pdfplumber

TREN = re.compile(r"^(20|22|50|60)\d{3}$")
TIME = re.compile(r"^\d{1,2}:\d{2}$")
KM = re.compile(r"^\d{1,3}[,.]\d$")
X_KM = 100        # km/dist parcial estan a la izquierda de x=100
X_NAME = 200      # nombre de estacion entre 100 y 200


def _rows(words, tol=3):
    R = []
    for w in sorted(words, key=lambda w: w["top"]):
        for r in R:
            if abs(r[0]["top"] - w["top"]) <= tol:
                r.append(w); break
        else:
            R.append([w])
    for r in R:
        r.sort(key=lambda w: w["x0"])
    return R


def _to_min(t):
    h, m = t.split(":")[:2]
    return int(h) * 60 + int(m)


def extraer(pdf_path, portador):
    filas = []
    seq = {}     # tren -> contador de orden global
    with pdfplumber.open(pdf_path) as pdf:
        for pg in pdf.pages:
            words = pg.extract_words()
            R = _rows(words)
            km_rows = [r for r in R if any(KM.fullmatch(w["text"]) for w in r)]
            if not km_rows:
                continue
            y_first_km = km_rows[0][0]["top"]
            # encabezado de trenes: fila con mas TREN por encima de la 1a fila km
            cand = [r for r in R if r[0]["top"] < y_first_km and len([w for w in r if TREN.fullmatch(w["text"])]) >= 1]
            if not cand:
                continue
            header = max(cand, key=lambda r: len([w for w in r if TREN.fullmatch(w["text"])]))
            trenes = [(w["text"], (w["x0"] + w["x1"]) / 2) for w in header if TREN.fullmatch(w["text"])]
            if not trenes:
                continue
            for r in km_rows:
                nombre = " ".join(w["text"] for w in r if X_KM < w["x0"] < X_NAME
                                  and re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]", w["text"]))
                nombre = re.sub(r"\s+", " ", nombre).strip()
                if len(nombre) < 3:
                    continue
                tiempos = [(w["x0"], w["text"]) for w in r if TIME.fullmatch(w["text"])]
                for tren, xc in trenes:
                    # Sale ~ centro del tren; Llega ~ 32px a la izquierda
                    cerca = sorted([(x, t) for (x, t) in tiempos if abs(x - xc) < 40 or abs(x - (xc - 32)) < 40])
                    if not cerca:
                        continue
                    cerca.sort()
                    lleg = _to_min(cerca[0][1])
                    sal = _to_min(cerca[1][1]) if len(cerca) > 1 else lleg
                    seq[tren] = seq.get(tren, 0) + 1
                    filas.append({
                        "fuente": "carga", "portador": portador, "tramo": "carga",
                        "sentido": "", "tipo_dia": "", "servicio": tren, "unidad": "",
                        "equipo_vacio": False, "estacion": nombre, "orden": seq[tren],
                        "llegada_min": lleg, "salida_min": sal})
    return pd.DataFrame(filas)


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).resolve().parents[1] / "parsers"))
    from config import ITIN_DIR
    fe = extraer(ITIN_DIR / "2-416. Programa Resto del Año 2026 FEPASA V2.pdf", "FEPASA")
    tr = extraer(ITIN_DIR / "2-421. Programa Resto del Año 2026 TRANSAP V2.pdf", "TRANSAP")
    df = pd.concat([fe, tr], ignore_index=True)
    print(f"Filas carga: {len(df)} | trenes: {df['servicio'].nunique()} | por portador:")
    print(df.groupby('portador')['servicio'].nunique().to_string())
    print("\nValidacion TRANSAP 60500 (primeras paradas):")
    v = df[(df.portador=='TRANSAP')&(df.servicio=='60500')].sort_values('orden')
    print(v[['estacion','llegada_min','salida_min']].head(6).to_string(index=False))
    print("\nEstaciones distintas (muestra):", sorted(df['estacion'].unique())[:20])
