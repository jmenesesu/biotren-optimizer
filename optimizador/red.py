"""Definicion de la red Biotren como arbol con Concepcion como nodo central.

Tres ramas desde Concepcion:
  - Rama Hualqui (lado oriente de L1)
  - Rama Mercado  (lado poniente de L1, hacia Talcahuano)
  - Rama Coronel  (L2)

Lineas de servicio:
  - L1: Mercado <-> Hualqui (atraviesa Concepcion): ramas Mercado + Hualqui.
  - L2: Concepcion <-> Coronel: rama Coronel.

Provee el mapeo estacion -> (rama, indice) y la ruta (lista de enlaces
dirigidos por linea) de cada par origen-destino, para construir las
restricciones de capacidad del optimizador.
"""

# Ramas: orden de estaciones DESDE Concepcion hacia afuera (nombres como en la matriz OD)
RAMA = {
    "Hualqui": ["Concepción", "Chiguayante", "Pedro Medina", "Manquimávida", "La Leonera", "Hualqui"],
    "Mercado": ["Concepción", "Mall", "Lzo. Arenas", "UTF Santa María", "Los Cóndores", "Higueras", "El Arenal", "Mercado"],
    "Coronel": ["Concepción", "Juan Pablo II", "Diagonal Bio Bio", "Alborada", "Costa Mar",
                "El Parque", "Lomas Coloradas", "Cdal. Raúl Silva Henríquez", "Hito Galvarino",
                "Los Canelos", "Huinca", "Cristo Redentor", "Laguna Quiñenco", "Coronel"],
}

# Linea que opera cada rama
LINEA_DE_RAMA = {"Hualqui": "L1", "Mercado": "L1", "Coronel": "L2"}

HUB = "Concepción"


def mapa_estaciones():
    """estacion -> (rama, indice desde Concepcion)."""
    m = {}
    for rama, ests in RAMA.items():
        for i, e in enumerate(ests):
            if e == HUB:
                m[e] = ("HUB", 0)
            else:
                m[e] = (rama, i)
    m[HUB] = ("HUB", 0)
    return m


MAPA = mapa_estaciones()


def _links_rama(rama, i_from, i_to):
    """Enlaces dirigidos (linea, rama, k, sentido) entre indices de una rama.

    k identifica el segmento entre la estacion k y k+1 (k>=0, donde 0 = Concepcion-1a).
    sentido: 'out' (alejandose de Concepcion) o 'in' (hacia Concepcion).
    """
    linea = LINEA_DE_RAMA[rama]
    links = []
    if i_from < i_to:        # alejandose del hub
        for k in range(i_from, i_to):
            links.append((linea, rama, k, "out"))
    else:                    # hacia el hub
        for k in range(i_from, i_to, -1):
            links.append((linea, rama, k - 1, "in"))
    return links


def ruta(origen, destino):
    """Lista de enlaces dirigidos que recorre un viaje origen->destino.

    Devuelve [] si alguna estacion no esta mapeada.
    """
    if origen not in MAPA or destino not in MAPA:
        return []
    ro, io = MAPA[origen]
    rd, idd = MAPA[destino]

    # origen = hub
    if ro == "HUB" and rd != "HUB":
        return _links_rama(rd, 0, idd)
    if rd == "HUB" and ro != "HUB":
        return _links_rama(ro, io, 0)
    if ro == "HUB" and rd == "HUB":
        return []
    if ro == rd:             # misma rama
        return _links_rama(ro, io, idd)
    # ramas distintas: origen -> hub -> destino
    return _links_rama(ro, io, 0) + _links_rama(rd, 0, idd)


def todos_los_enlaces():
    """Conjunto de todos los enlaces dirigidos de la red."""
    enlaces = set()
    for rama, ests in RAMA.items():
        linea = LINEA_DE_RAMA[rama]
        for k in range(len(ests) - 1):
            enlaces.add((linea, rama, k, "out"))
            enlaces.add((linea, rama, k, "in"))
    return enlaces


if __name__ == "__main__":
    print("Estaciones mapeadas:", len(MAPA))
    print("Enlaces dirigidos:", len(todos_los_enlaces()))
    for o, d in [("Hualqui", "Concepción"), ("Coronel", "Concepción"),
                 ("Hualqui", "Coronel"), ("Mercado", "Hualqui"),
                 ("Lomas Coloradas", "Juan Pablo II")]:
        r = ruta(o, d)
        lineas = sorted(set(x[0] for x in r))
        print(f"{o} -> {d}: {len(r)} enlaces, lineas {lineas}")
