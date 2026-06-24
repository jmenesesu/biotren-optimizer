"""Motor de señalización (aspectos) según RTF / Manual CTC NOV 2017 (apartado 2.4.1).

Implementa el block de 3 aspectos con seguimiento:
  - Cada cantón está protegido por una señal en su entrada (por sentido).
  - Regla CTC (señales de seguimiento): "detrás de cada tren una señal en ROJO, la
    anterior en AMARILLO y la siguiente en VERDE".
  - Aspecto de la señal que protege un cantón C (en el sentido de marcha):
        ROJO     si C está ocupado (hay un tren en C),
        AMARILLO si C libre pero el cantón siguiente (adelante) está ocupado,
        VERDE    si C y el siguiente están libres.
  - Señales con Rojo = Absolutas: un tren no puede rebasarlas (se detiene).
Con esto se determina la OCUPACIÓN de vía (cantones con tren) y las reglas de
movimiento (un tren no entra a un cantón cuya señal de protección esté en Rojo).

Tipos de señal (RTF/CTC 2.4.1): Entrada (E), Salida (S), Salida Interior,
Seguimiento (Nº/PK), Avanzada Absoluta (E').
"""
import sys
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO / "parsers"))
from config import CLEAN  # noqa: E402

ROJO, AMARILLO, VERDE = "Rojo", "Amarillo", "Verde"


def cantones(linea):
    b = pd.read_csv(CLEAN / "bloques.csv")
    g = b[b.linea == linea].sort_values("dist_lo").reset_index(drop=True)
    return [(float(r.dist_lo), float(r.dist_hi)) for r in g.itertuples()]


def _ocupado(lo, hi, posiciones):
    return any(lo - 1e-6 <= d <= hi + 1e-6 for d in posiciones)


def aspectos(linea, posiciones, sentido="creciente"):
    """Aspecto de la señal que protege la ENTRADA de cada cantón, en el sentido dado.

    posiciones: lista de km de los trenes presentes en la línea.
    sentido: 'creciente' (→, km crece) o 'decreciente' (←).
    Devuelve lista de dicts {km_senal, cl, ch, aspecto} ordenada por avance.
    """
    cs = cantones(linea)
    if sentido == "decreciente":
        cs = list(reversed(cs))
    ocup = [_ocupado(lo, hi, posiciones) for lo, hi in cs]
    out = []
    for i, (lo, hi) in enumerate(cs):
        # señal en la entrada del cantón i, según sentido de marcha
        km_senal = lo if sentido == "creciente" else hi
        sig = ocup[i + 1] if i + 1 < len(cs) else False   # cantón siguiente (adelante)
        if ocup[i]:
            asp = ROJO
        elif sig:
            asp = AMARILLO
        else:
            asp = VERDE
        out.append({"linea": linea, "km": round(km_senal, 3),
                    "canton_lo": round(lo, 3), "canton_hi": round(hi, 3),
                    "sentido": sentido, "aspecto": asp})
    return out


def vias_ocupadas(linea, posiciones):
    """Cantones (vías) ocupados por un tren — lo que el CTC ve por circuitos de vía."""
    return [{"linea": linea, "canton_lo": round(lo, 3), "canton_hi": round(hi, 3)}
            for lo, hi in cantones(linea) if _ocupado(lo, hi, posiciones)]


if __name__ == "__main__":
    # demo: dos trenes en L2 y los aspectos resultantes
    pos = [11.0, 19.5]
    print("Vías (cantones) ocupadas en L2 con trenes en km", pos, ":")
    for v in vias_ocupadas("L2", pos):
        print("  ", v["canton_lo"], "-", v["canton_hi"])
    print("\nAspectos (sentido creciente →), primeros con Rojo/Amarillo:")
    for a in aspectos("L2", pos, "creciente"):
        if a["aspecto"] != VERDE:
            print(f"  señal km {a['km']} protege cantón {a['canton_lo']}-{a['canton_hi']}: {a['aspecto']}")
