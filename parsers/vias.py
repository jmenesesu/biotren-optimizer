"""Modelo de vías por tramo y enlaces (agujas) desde OpenTrack (Metrolinx).

Clasifica cada tramo de una línea como VÍA ÚNICA o DOBLE VÍA según cuántas vías
"Principal" paralelas existan, y localiza los enlaces (agujas) reales. Permite la
operación con vía derecha por sentido y el uso de enlaces para cambiar de vía.

Convención de vía derecha (sentido de la marcha):
  L2 corre N–S con el mar (poniente) al oeste:
    - sentido sur (CC->CW, km creciente): vía DERECHA = Principal poniente.
    - sentido norte (CW->CC, km decreciente): vía DERECHA = Principal oriente.

Salida:
  datos/clean/tramos_via.csv  (linea, km_lo, km_hi, n_vias, tipo, vias)
  datos/clean/enlaces.csv     (linea, km, n_agujas)
"""
import sys
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO / "parsers"))
from config import CLEAN  # noqa: E402

GRUPO = {"L01-BB-LM": "L2", "L02-ES-CW": "L2",
         "K01-BU-GO": "L1", "K02-TL-UN": "L1", "K03-QU-HQ": "L1",
         "K-04-OH-ZW-CV 1": "L1", "K05-CC": "L1", "K-06-EZ-TH 1": "L1"}
# vía derecha por sentido (en doble vía): nombre de la vía Principal
DERECHA = {"CC->CW": "poniente", "CW->CC": "oriente",
           "TH->LJ": "poniente", "LJ->TH": "oriente"}


def _cobertura(e, linea, lado):
    """Intervalos de km cubiertos por aristas de vía Principal de un lado
    (oriente/poniente), fusionados. Usa la cobertura REAL por arista (no min/max),
    de modo que los huecos sin doble vía registrada queden visibles."""
    sub = e[e.document.map(GRUPO.get) == linea]
    ivs = []
    for tr in sub.track.dropna().unique():
        if "rincipal" not in str(tr) or lado not in str(tr):
            continue
        gt = sub[sub.track == tr]
        for r in gt.itertuples():
            if pd.notna(r.v1_km) and pd.notna(r.v2_km):
                ivs.append((min(r.v1_km, r.v2_km), max(r.v1_km, r.v2_km)))
    ivs.sort()
    fus = []
    for lo, hi in ivs:
        if fus and lo <= fus[-1][1] + 2.5:   # une huecos de patio (<1.5 km)
            fus[-1] = (fus[-1][0], max(fus[-1][1], hi))
        else:
            fus.append((lo, hi))
    return fus


def _en(ivs, x):
    return any(a - 1e-6 <= x <= b + 1e-6 for a, b in ivs)


def construir(linea="L2", km_min=None, km_max=None):
    e = pd.read_csv(CLEAN / "infra_edges.csv")
    ori = _cobertura(e, linea, "oriente")
    pon = _cobertura(e, linea, "poniente")
    bps = sorted(set([round(x, 2) for iv in ori + pon for x in iv]))
    if km_min is not None:
        bps = [b for b in bps if km_min - 0.5 <= b <= (km_max or 1e9) + 0.5]
    filas = []
    for i in range(len(bps) - 1):
        lo, hi = bps[i], bps[i + 1]
        if hi - lo < 0.05:
            continue
        mid = (lo + hi) / 2
        o, p = _en(ori, mid), _en(pon, mid)
        if o and p:
            tipo, n, vias = "doble", 2, "oriente; poniente"
        elif o or p:
            tipo, n, vias = "única", 1, ("oriente" if o else "poniente")
        else:
            tipo, n, vias = "no determinado", 1, "sin doble vía registrada"
        filas.append({"linea": linea, "km_lo": lo, "km_hi": hi, "n_vias": n, "tipo": tipo, "vias": vias})
    tv = pd.DataFrame(filas)
    # enlaces (agujas) agrupados
    sub = e[e.document.map(GRUPO.get) == linea]
    sw = sub[(sub.v1_switch_time.notna()) | (sub.v2_switch_time.notna())]
    ak = sorted(set(round(k, 1) for k in pd.concat([sw.v1_km, sw.v2_km]).dropna()))
    enl = pd.DataFrame({"linea": linea, "km": ak, "n_agujas": 1})
    return tv, enl


def main():
    tvs, enls = [], []
    for ln in ["L2"]:
        tv, enl = construir(ln, km_min=1, km_max=28)
        tvs.append(tv); enls.append(enl)
    pd.concat(tvs, ignore_index=True).to_csv(CLEAN / "tramos_via.csv", index=False)
    pd.concat(enls, ignore_index=True).to_csv(CLEAN / "enlaces.csv", index=False)
    return tvs[0], enls[0]


if __name__ == "__main__":
    tv, enl = main()
    print("=== Tramos de vía L2 ===")
    print(tv.to_string(index=False))
    print(f"\nEnlaces (agujas) L2: {len(enl)} → {list(enl.km)}")
