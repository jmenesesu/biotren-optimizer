"""Parser de programas de trenes de carga (FEPASA 2-416 y TRANSAP 2-421).

Extrae los caminos de cada tren de carga: por tren, la secuencia de estaciones
con hora de llegada y salida. Usa coordenadas de palabras (pdfplumber) para
asignar cada hora a la columna de su tren.

Estos caminos son restricciones fijas: ocupan tramos (en particular de vía única)
en ventanas horarias que el optimizador debe respetar.

Uso:
    python parsers/parse_freight.py
Salida:
    datos/clean/carga_caminos.csv   (portador, tren, estacion, llegada, salida)
"""
import re
import pandas as pd
import pdfplumber
from config import ITIN_DIR, CLEAN

PDFS = {
    "FEPASA": ITIN_DIR / "2-416. Programa Resto del Año 2026 FEPASA V2.pdf",
    "TRANSAP": ITIN_DIR / "2-421. Programa Resto del Año 2026 TRANSAP V2.pdf",
}

TREN_RE = re.compile(r"^(?:20|22|50|60)\d{3}$")   # números de tren de carga / cruces
TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")
# token de estación: contiene al menos 3 letras
STA_RE = re.compile(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{3,}")


def _rows_by_y(words, tol=3):
    """Agrupa palabras en filas por su coordenada vertical."""
    rows = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        placed = False
        for r in rows:
            if abs(r[0]["top"] - w["top"]) <= tol:
                r.append(w); placed = True; break
        if not placed:
            rows.append([w])
    for r in rows:
        r.sort(key=lambda w: w["x0"])
    return rows


def _parse_page(page):
    words = page.extract_words()
    rows = _rows_by_y(words)

    # 1) localizar columnas de tren (fila con varios números de tren)
    columnas = []  # (numero, x_centro)
    for r in rows:
        nums = [w for w in r if TREN_RE.fullmatch(w["text"])]
        if len(nums) >= 1 and len(nums) >= len([w for w in r if STA_RE.search(w["text"])]):
            for w in nums:
                columnas.append((w["text"], (w["x0"] + w["x1"]) / 2))
    if not columnas:
        return []
    # ordenar columnas por x
    columnas.sort(key=lambda c: c[1])
    centros = [c[1] for c in columnas]
    trenes = [c[0] for c in columnas]

    def col_idx(x):
        # columna más cercana
        return min(range(len(centros)), key=lambda i: abs(centros[i] - x))

    # 2) filas de estación: tienen nombre + tiempos
    registros = []
    for r in rows:
        nombre_toks = [w for w in r if STA_RE.search(w["text"]) and not TREN_RE.fullmatch(w["text"])]
        tiempos = [w for w in r if TIME_RE.fullmatch(w["text"])]
        if not nombre_toks or not tiempos:
            continue
        # nombre = tokens de texto a la izquierda del primer tiempo
        x_primer_tiempo = min(w["x0"] for w in tiempos)
        nombre = " ".join(w["text"] for w in nombre_toks if w["x1"] < x_primer_tiempo)
        nombre = nombre.strip()
        if len(nombre) < 3:
            continue
        # agrupar tiempos por columna de tren; el de menor x = llegada, mayor x = salida
        por_col = {}
        for w in tiempos:
            i = col_idx((w["x0"] + w["x1"]) / 2)
            por_col.setdefault(i, []).append(w)
        for i, ws in por_col.items():
            ws.sort(key=lambda w: w["x0"])
            llegada = ws[0]["text"] if len(ws) >= 1 else None
            salida = ws[1]["text"] if len(ws) >= 2 else None
            registros.append({
                "tren": trenes[i], "estacion": nombre,
                "llegada": llegada, "salida": salida,
            })
    return registros


def parse():
    todos = []
    for portador, pdf_path in PDFS.items():
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                for rec in _parse_page(page):
                    rec["portador"] = portador
                    todos.append(rec)
    df = pd.DataFrame(todos, columns=["portador", "tren", "estacion", "llegada", "salida"])
    df = df.drop_duplicates().reset_index(drop=True)
    df.to_csv(CLEAN / "carga_caminos.csv", index=False)
    return df


if __name__ == "__main__":
    df = parse()
    print(f"Registros (tren-estación) extraídos: {len(df)}")
    print(f"Trenes de carga distintos: {df['tren'].nunique()}")
    print("Por portador:")
    print(df.groupby("portador")["tren"].nunique().to_string())
    print("\nEjemplo de un tren:")
    t0 = df["tren"].iloc[0]
    print(df[df.tren == t0].head(12).to_string(index=False))
    print(f"\nGuardado en: {CLEAN}")
    print("NOTA: extracción aproximada por coordenadas; validar contra el PDF "
          "antes de usar en producción (ver bitácora).")
