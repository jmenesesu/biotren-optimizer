"""Chequeos estructurales sobre horarios_limpios (deteccion de errores de extraccion).

Checks precisos (bajo falso positivo):
  1. monotonia: los tiempos no retroceden a lo largo del recorrido (siempre error).
  2. orden canonico: las estaciones del servicio aparecen en el MISMO orden relativo
     que la secuencia oficial de la linea (detecta reordenes/saltos de extraccion;
     NO penaliza short-turns, que son un subconjunto contiguo valido).
  3. velocidad por tramo: la velocidad implicada entre estaciones consecutivas debe
     ser plausible (<= 120 km/h); valores absurdos delatan tiempos mal asignados.
  4. dwell: salida >= llegada en cada estacion.
No se imponen origen/terminal fijos (hay short-turns reales) ni banda de tiempo
total (hay expresos reales).
"""
import sys
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
CLEAN = REPO / "datos" / "clean"
sys.path.append(str(REPO / "optimizador"))
from ejes_distancia import ORDEN_L1, ORDEN_L2  # noqa: E402

CANON = {"CC->CW": ORDEN_L2, "CW->CC": list(reversed(ORDEN_L2)),
         "TH->LJ": ORDEN_L1, "LJ->TH": list(reversed(ORDEN_L1))}
VMAX = 120.0   # km/h


def _km():
    import estaciones_maestro as em
    return em


def _norm(s):
    import unicodedata
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().upper().strip()


def _es_subsecuencia(sub, full):
    full = [_norm(x) for x in full]
    it = iter(full)
    return all(_norm(e) in it for e in sub)


def chequear():
    sys.path.append(str(REPO / "parsers"))
    import estaciones_maestro as em
    hl = pd.read_csv(CLEAN / "horarios_limpios.csv")
    issues = []
    pax = hl[hl.fuente == "pasajeros"]
    servicios = 0
    for (serv, sentido, td, vac), g in pax.groupby(["servicio", "sentido", "tipo_dia", "equipo_vacio"]):
        servicios += 1
        g = g.sort_values("orden")
        sid = f"pax {serv} {sentido} {td}" + (" [vacío]" if vac else "")
        ests = g["estacion"].tolist()
        lleg = g["llegada_min"].tolist(); sal = g["salida_min"].tolist()
        tramo = g["tramo"].iloc[0]
        # 1 monotonia
        seq = []
        for l, s in zip(lleg, sal):
            seq += [l, s]
        if any(seq[i+1]-seq[i] < -1e-6 for i in range(len(seq)-1)):
            issues.append((sid, "monotonia", "tiempos retroceden"))
        # 2 orden canonico (solo servicios regulares; los vacios reposicionan)
        canon = CANON.get(sentido)
        if canon and not vac and not _es_subsecuencia(ests, canon):
            issues.append((sid, "orden", f"estaciones fuera de orden: {ests[:5]}"))
        # 3 velocidad por tramo
        for i in range(len(ests)-1):
            k1 = em.resolver_km(ests[i], tramo); k2 = em.resolver_km(ests[i+1], tramo)
            dt = (lleg[i+1] - sal[i]) / 60.0
            if k1 is not None and k2 is not None and dt > 0:
                v = abs(k2 - k1) / dt
                if v > VMAX:
                    issues.append((sid, "velocidad", f"{ests[i]}->{ests[i+1]}: {v:.0f} km/h"))
        # 4 dwell
        for e, l, s in zip(ests, lleg, sal):
            if s - l < -1e-6:
                issues.append((sid, "dwell<0", f"{e}: salida<llegada"))
    # vacios fuera de orden canonico (informativo)
    vac_oo = 0
    for (serv, sentido, td, vac), g in pax.groupby(["servicio", "sentido", "tipo_dia", "equipo_vacio"]):
        if not vac:
            continue
        canon = CANON.get(sentido)
        if canon and not _es_subsecuencia(g.sort_values("orden")["estacion"].tolist(), canon):
            vac_oo += 1
    # carga: solo monotonia (informativa; mezcla rutas)
    carga = hl[hl.fuente == "carga"]
    n_carga_mono = 0
    for (port, serv), g in carga.groupby(["portador", "servicio"]):
        g = g.sort_values("orden")
        seq = []
        for l, s in zip(g["llegada_min"], g["salida_min"]):
            seq += [l, s]
        if any(seq[i+1]-seq[i] < -1e-6 for i in range(len(seq)-1)):
            n_carga_mono += 1
    return issues, servicios, carga["servicio"].nunique(), n_carga_mono, vac_oo


if __name__ == "__main__":
    import collections
    issues, n_pax, n_carga, carga_mono, vac_oo = chequear()
    serv_con = len(set(i[0] for i in issues))
    print(f"Pasajeros (servicio x sentido x día): {n_pax}")
    print(f"  con incidencia: {serv_con}  ->  tasa de coincidencia limpia: {100*(n_pax-serv_con)/n_pax:.1f}%")
    print(f"Incidencias pasajeros: {len(issues)}")
    for k, v in collections.Counter(t for _, t, _ in issues).most_common():
        print(f"  {k}: {v}")
    print(f"\nEquipos en vacío fuera de orden canónico: {vac_oo} (esperable: reposicionan).")
    print(f"Carga: {n_carga} trenes; {carga_mono} con tiempos no monótonos "
          f"(esperable: mezclan rutas/continuaciones).")
    print("\nDetalle pasajeros:")
    for sid, t, d in issues[:30]:
        print(f"  [{t}] {sid} — {d}")
    pd.DataFrame(issues, columns=["servicio", "tipo", "detalle"]).to_csv(
        REPO / "validacion" / "incidencias_estructurales.csv", index=False)
