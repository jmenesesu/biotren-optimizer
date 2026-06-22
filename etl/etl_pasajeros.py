"""ETL itinerario de PASAJEROS (PDF 2-410) -> tabla limpia de horarios.

Extrae los tiempos REALES por estacion y servicio desde la grilla del PDF
(no reconstruidos): por cada servicio y estacion, hora de LLEGADA y SALIDA,
mas: numero de servicio, automotor asignado, equipo vacio (si/no), tipo de dia,
tramo (L1/L2) y sentido.

Cada pagina tiene 2 tablas (un sentido arriba, otro abajo); se procesa por tabla.

Salida (al unificar): filas con esquema comun. Aqui devuelve un DataFrame.
"""
import re
import pandas as pd
import pdfplumber

SERV = re.compile(r"^20\d{3}$")
T_HMS = re.compile(r"^\d{1,2}:\d{2}:\d{2}$")     # llegada/salida comercial
T_HM = re.compile(r"^\d{1,2}:\d{2}$")            # equipos vacios / terminal
UNIDAD = re.compile(r"^(SFE|UT)$")
NUMUN = re.compile(r"^(B?\d{1,2})$")

# estaciones validas por tramo (nombre tal como aparece como etiqueta de fila)
EST_L2 = ["CONCEPCIÓN", "Juan Pablo II", "Diagonal Bio Bio", "Alborada", "Costa Mar",
          "El Parque", "LOMAS COLORADAS", "Card. Raúl Silva Henriquez", "Hito Galvarino",
          "Los Canelos", "Huinca", "Cristo Redentor", "Laguna Quiñenco", "CORONEL"]
EST_L1 = ["LAJA", "SAN ROSENDO", "BUENURAQUI", "GOMERO", "TALCAMÁVIDA", "Los Acacios",
          "Valle Chanco", "UNIHUE", "San Miguel", "QUILACOYA", "HUALQUI", "OMER HUET",
          "LA LEONERA", "Manquimávida", "Pedro Medina", "CHIGUAYANTE", "CONCEPCIÓN",
          "Lorenzo Arenas", "UTF Santa María", "Los Cóndores", "Hospital Las Higueras",
          "EL ARENAL", "Mercado"]


def _norm(s):
    return re.sub(r"\s+", " ", s).strip()


def _to_min(t):
    p = [int(x) for x in t.split(":")]
    if len(p) == 3:
        return p[0] * 60 + p[1] + p[2] / 60.0
    return p[0] * 60 + p[1]


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


def _tipo_dia(texto):
    if "Sábado" in texto and "Domingo" not in texto:
        return "Sábado"
    if "Domingo" in texto:
        return "Domingo"
    return "Lun-Vie"


def _label(r, xmax=150):
    return _norm("".join(w["text"] + " " for w in r if w["x0"] < xmax))


def _match_est(label, tramo):
    ests = EST_L2 if tramo == "L2" else EST_L1
    lu = label.upper()
    for e in ests:
        if lu.startswith(e.upper()[:8]):
            return e
    return None


def extraer(pdf_path):
    filas = []
    with pdfplumber.open(pdf_path) as pdf:
        for pg in pdf.pages:
            words = pg.extract_words()
            texto = " ".join(w["text"] for w in words)
            tramo = "L2" if "CONCEPCIÓN-CORONEL" in texto else ("L1" if "LAJA-TALCAHUANO" in texto else None)
            if tramo is None:
                continue
            dia = _tipo_dia(texto)
            R = _rows(words)
            tren_rows = [(r[0]["top"], r) for r in R
                          if len(set(w["text"] for w in r if SERV.fullmatch(w["text"]))) >= 8]
            tren_rows.sort()
            ys = [y for y, _ in tren_rows] + [1e9]
            for ti, (ytren, trow) in enumerate(tren_rows):
                y0, y1 = ytren, ys[ti + 1]
                region = [r for r in R if y0 - 1 <= r[0]["top"] < y1]
                servs = sorted([(w["text"], (w["x0"] + w["x1"]) / 2) for w in trow if SERV.fullmatch(w["text"])],
                               key=lambda x: x[1])
                if not servs:
                    continue
                # equipo vacio: token 'VAC' arriba del tren row, por columna
                vacios = set()
                for w in words:
                    if "VAC" in w["text"].upper() and ytren - 30 < w["top"] < ytren:
                        xc = (w["x0"] + w["x1"]) / 2
                        s = min(servs, key=lambda v: abs(v[1] - xc))
                        if abs(s[1] - xc) < 35:
                            vacios.add(s[0])
                # unidad por servicio
                unidades = {}
                for r in region:
                    if 0 < r[0]["top"] - ytren < 30:
                        for i, w in enumerate(r):
                            if UNIDAD.fullmatch(w["text"]) and i + 1 < len(r) and NUMUN.fullmatch(r[i + 1]["text"]):
                                xc = (w["x0"] + r[i + 1]["x1"]) / 2
                                s = min(servs, key=lambda v: abs(v[1] - xc))
                                if abs(s[1] - xc) < 35:
                                    unidades[s[0]] = f"{w['text']} {r[i+1]['text']}"
                # determinar sentido por la primera estacion con tiempos
                est_rows = []
                for r in region:
                    est = _match_est(_label(r), tramo)
                    tms = [w for w in r if (T_HMS.fullmatch(w["text"]) or T_HM.fullmatch(w["text"])) and w["x0"] > 190]
                    if est and tms:
                        est_rows.append((r[0]["top"], est, r, tms))
                if not est_rows:
                    continue
                est_rows.sort()
                origen = est_rows[0][1]
                sentido = {"CONCEPCIÓN": "CC->CW", "CORONEL": "CW->CC",
                           "Mercado": "TH->LJ", "LAJA": "LJ->TH",
                           "SAN ROSENDO": "LJ->TH"}.get(origen, "?")
                orden = 0
                centros = [c for _, c in servs]
                n = len(servs)
                for _, est, r, tms in est_rows:
                    tms_sorted = sorted(tms, key=lambda w: w["x0"])
                    xcs = [(w["x0"] + w["x1"]) / 2 for w in tms_sorted]
                    # filas con ~1 tiempo por servicio (terminal) suelen estar
                    # desplazadas ~media columna -> se estima el shift; las filas con
                    # pares LLEGA/SALE (~2N) se emparejan por cercania (shift 0).
                    if len(tms_sorted) <= 1.4 * n:
                        mejor = (0.0, 1e18)
                        for shift in range(-10, 56, 2):
                            err = sum(min(abs((x - shift) - c) for c in centros) for x in xcs)
                            if err < mejor[1]:
                                mejor = (shift, err)
                        shift = mejor[0]
                    else:
                        shift = 0.0
                    por_serv = {}
                    for w, xc in zip(tms_sorted, xcs):
                        sv = min(servs, key=lambda v: abs(v[1] - (xc - shift)))
                        if abs(sv[1] - (xc - shift)) < 28:
                            por_serv.setdefault(sv[0], []).append((w["x0"], w["text"]))
                    for serv, lst in por_serv.items():
                        lst.sort()
                        tiempos = [t for _, t in lst]
                        lleg = _to_min(tiempos[0])
                        sal = _to_min(tiempos[1]) if len(tiempos) > 1 else lleg
                        filas.append({
                            "fuente": "pasajeros", "portador": "EFE", "tramo": tramo,
                            "sentido": sentido, "tipo_dia": dia, "servicio": serv,
                            "unidad": unidades.get(serv, ""), "equipo_vacio": serv in vacios,
                            "estacion": est, "orden": orden,
                            "llegada_min": round(lleg, 2), "salida_min": round(sal, 2)})
                    orden += 1
    df = pd.DataFrame(filas)
    return df


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).resolve().parents[1] / "parsers"))
    from config import ITIN_DIR
    df = extraer(ITIN_DIR / "2-410. Itinerario Pasajeros Concepción 30-mar-2026.pdf")
    print(f"Filas: {len(df)} | servicios: {df['servicio'].nunique()} | dias: {df['tipo_dia'].unique()}")
    print("Por tramo/sentido/dia (servicios):")
    print(df.groupby(['tramo','sentido','tipo_dia'])['servicio'].nunique().to_string())
    print("\nValidacion 20001 (Lun-Vie L2 CC->CW):")
    v = df[(df.servicio=='20001')&(df.tipo_dia=='Lun-Vie')].sort_values('orden')
    print(v[['estacion','llegada_min','salida_min','unidad','equipo_vacio']].head(4).to_string(index=False))
