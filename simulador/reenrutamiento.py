"""Re-enrutamiento por enlaces DIRIGIDOS.

Un tren solo puede cambiar de vía en un enlace (escape) válido para su SENTIDO de
marcha (regla de punta/talón). Este motor responde: si un tren que circula por su
vía debe cambiarse a la otra (para cruzar en vía única, adelantar, o porque su vía
está ocupada/bloqueada), ¿en qué enlace puede hacerlo y cuál es el más cercano
adelante en su sentido?

Usa datos/clean/enlaces_dirigidos.csv (leídos de la Tira Larga).
"""
import sys
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO / "parsers"))
from config import CLEAN  # noqa: E402


def cargar(linea="L2"):
    f = CLEAN / "enlaces_dirigidos.csv"
    if not f.exists():
        return pd.DataFrame()
    d = pd.read_csv(f)
    return d[d.linea == linea]


def via_de(sentido):
    """vía por la que circula un tren según su sentido (circulación por la derecha)."""
    return "der" if sentido in ("CC->CW", "LJ->TH") else "izq"


def enlace_para_cambio(linea, km, sentido, hacia=None):
    """Enlace más cercano ADELANTE (en el sentido de marcha) que permite a un tren
    cambiar de su vía a la otra. Devuelve dict o None.

    - km: posición actual del tren (km maestro).
    - sentido: CC->CW / CW->CC / LJ->TH / TH->LJ.
    """
    enl = cargar(linea)
    if enl.empty:
        return None
    va = via_de(sentido)                 # vía actual
    vd = "izq" if va == "der" else "der"  # vía destino
    creciente = sentido in ("CC->CW", "LJ->TH")
    # movimientos válidos: desde va hacia vd, para este sentido (der/izq de circulación)
    cand = enl[(enl.via_origen == va) & (enl.via_destino == vd) & (enl.sentido == va)]
    # adelante en el sentido de marcha
    if creciente:
        cand = cand[cand.km >= km - 1e-6].sort_values("km")
    else:
        cand = cand[cand.km <= km + 1e-6].sort_values("km", ascending=False)
    if cand.empty:
        return None
    r = cand.iloc[0]
    return {"estacion": r.estacion, "km": float(r.km), "agujas": r.agujas,
            "via_origen": r.via_origen, "via_destino": r.via_destino, "tipo": r.tipo}


if __name__ == "__main__":
    print("Enlaces dirigidos L2:")
    print(cargar("L2")[["estacion", "km", "via_origen", "via_destino", "sentido"]].to_string(index=False))
    print("\nEjemplos de re-enrutamiento:")
    casos = [(5.0, "CC->CW"), (5.0, "CW->CC"), (25.0, "CW->CC"), (12.0, "CC->CW")]
    for km, se in casos:
        e = enlace_para_cambio("L2", km, se)
        va = via_de(se)
        if e:
            print(f"  Tren en km {km} ({se}, vía {va}) que deba cambiar de vía -> "
                  f"escape en {e['estacion']} km {e['km']} ({e['agujas']})")
        else:
            print(f"  Tren en km {km} ({se}, vía {va}) -> no hay escape válido adelante")
