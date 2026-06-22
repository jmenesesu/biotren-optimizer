"""Etapa 2 (refinado a hora punta) — optimizador de frecuencias + flota.

Dimensiona a la HORA DE DISENO (punta) de cada franja, no al promedio. De la
demanda OD por franja se obtiene la demanda de la hora punta aplicando un factor
de participacion (share) documentado por franja. El MILP MAXIMIZA la demanda de
hora punta servida decidiendo la frecuencia horaria por linea y franja, sujeto a:
  - Capacidad por enlace: demanda servida <= servicios_hora * 780.
  - Frecuencia horaria acotada por la via unica (headway minimo).
  - Flota: trenes = freq_hora * ciclo / 60; suma <= 16 por franja.
  - Limite electrico por subestacion (trenes simultaneos).

Asi el modelo refleja el cuello de botella real (la rush) y dimensiona la flota
al pico, respondiendo si los 16 automotores efectivamente alcanzan.

Uso:
    python optimizador/optimizar_capacidad.py
Salida:
    datos/clean/optim_frecuencias.csv
    datos/clean/optim_resumen.json
"""
import json
import sys
from pathlib import Path
import pandas as pd
import pulp

sys.path.append(str(Path(__file__).resolve().parents[1] / "parsers"))
from config import CLEAN, CAP_AUTOMOTOR, CONSUMO_A, TENSION_V  # noqa: E402
import red  # noqa: E402

# --- Parametros (supuestos documentados; editables) ---
FRANJAS_DUR = {"05-10": 300, "10-16": 360, "16-24": 480}   # minutos
# Participacion de la hora punta sobre el total de la franja (hora de diseno).
# Punta manana y punta tarde concentran mas; valle es mas plano.
PEAK_SHARE = {"05-10": 0.30, "10-16": 0.20, "16-24": 0.28}
FLOTA = 16
TURNAROUND_MIN = 6
HEADWAY_MIN = {"L1": 25, "L2": 9}     # via unica: L1 Hualqui-La Leonera, L2 Tunel Chepe
POT_TREN_MW = CONSUMO_A * TENSION_V / 1e6          # 0.6 MW
SER_TOTAL_MW = 3 + 3 + 3 + 6                        # 15 MW
N_MAX_ELEC = int(SER_TOTAL_MW // POT_TREN_MW)       # 25 trenes simultaneos


def cycle_times(itin):
    l2 = itin[(itin.tramo == "L2") & (itin.sentido == "CC->CW")]
    l2_ow = (l2["t_viaje_s"].sum() + l2["detencion_s"].fillna(0).sum()) / 60.0
    l1 = itin[(itin.tramo == "L1") & (itin.sentido == "LJ->TH")].reset_index(drop=True)
    i_hq = l1.index[l1.estacion.str.upper() == "HUALQUI"][0]
    span = l1.iloc[i_hq + 1:]
    l1_ow = (span["t_viaje_s"].sum() + span["detencion_s"].fillna(0).sum()) / 60.0
    return ({"L1": 2 * l1_ow + 2 * TURNAROUND_MIN, "L2": 2 * l2_ow + 2 * TURNAROUND_MIN},
            {"L1": round(l1_ow, 1), "L2": round(l2_ow, 1)})


def demanda_hora_punta(od):
    """Demanda de hora punta por par OD y franja, y su ruta (enlaces)."""
    dem, rutas = {}, {}
    for _, r in od.iterrows():
        ru = red.ruta(r.origen, r.destino)
        if not ru:
            continue
        key = (r.origen, r.destino, r.franja)
        dem[key] = r.viajes * PEAK_SHARE[r.franja]   # nivel hora punta
        rutas[key] = ru
    return dem, rutas


def carga_max_enlace(dem, rutas):
    """Demanda de hora punta del enlace mas cargado por (linea, franja)."""
    acum = {}
    for (o, d, fr), v in dem.items():
        for link in rutas[(o, d, fr)]:
            acum.setdefault((link[0], fr, link), 0.0)
            acum[(link[0], fr, link)] += v
    peak = {}
    for (linea, fr, link), v in acum.items():
        peak[(linea, fr)] = max(peak.get((linea, fr), 0.0), v)
    return peak


def sensibilidad_peak_share(od, itin, shares=(0.20, 0.30, 0.40, 0.50)):
    """Como cambia la flota pico necesaria segun el factor de hora punta."""
    global PEAK_SHARE
    base = dict(PEAK_SHARE)
    out = []
    for sh in shares:
        PEAK_SHARE = {k: sh for k in FRANJAS_DUR}
        _df, _res = _resolver(od, itin)
        out.append({"peak_share": sh,
                    "flota_pico": _res["flota_pico_usada"],
                    "cobertura_pct": _res["cobertura_pct"],
                    "suficiente_16": _res["flota_suficiente"]})
    PEAK_SHARE = base
    return out


def _resolver(od, itin):
    ciclo, oneway = cycle_times(itin)
    dem, rutas = demanda_hora_punta(od)
    peak_link = carga_max_enlace(dem, rutas)

    lineas = ["L1", "L2"]
    prob = pulp.LpProblem("Biotren_capacidad_punta", pulp.LpMaximize)

    fh = {(l, fr): pulp.LpVariable(f"fh_{l}_{fr}", lowBound=0, cat="Integer")
          for l in lineas for fr in FRANJAS_DUR}
    trains = {(l, fr): pulp.LpVariable(f"n_{l}_{fr}", lowBound=0, cat="Integer")
              for l in lineas for fr in FRANJAS_DUR}
    serv = {k: pulp.LpVariable(f"s_{i}", lowBound=0, upBound=v)
            for i, (k, v) in enumerate(dem.items())}

    prob += pulp.lpSum(serv.values()) - 0.001 * pulp.lpSum(trains.values()), "servida_punta"

    # 1) Capacidad por enlace dirigido en la hora punta
    for fr in FRANJAS_DUR:
        carga = {}
        for (o, d, frr), var in serv.items():
            if frr != fr:
                continue
            for link in rutas[(o, d, frr)]:
                carga.setdefault(link, []).append(var)
        for link, vars_ in carga.items():
            prob += pulp.lpSum(vars_) <= fh[(link[0], fr)] * CAP_AUTOMOTOR, \
                f"cap_{link[0]}_{link[1]}_{link[2]}_{link[3]}_{fr}"

    # 2) Frecuencia horaria acotada por la via unica
    for l in lineas:
        for fr in FRANJAS_DUR:
            prob += fh[(l, fr)] <= 60.0 / HEADWAY_MIN[l], f"via_unica_{l}_{fr}"

    # 3) Flota: trenes = freq_hora * ciclo / 60
    for l in lineas:
        for fr in FRANJAS_DUR:
            prob += trains[(l, fr)] >= fh[(l, fr)] * ciclo[l] / 60.0, f"flota_def_{l}_{fr}"

    # 4) Flota total y limite electrico por franja
    for fr in FRANJAS_DUR:
        prob += pulp.lpSum(trains[(l, fr)] for l in lineas) <= FLOTA, f"flota_{fr}"
        prob += pulp.lpSum(trains[(l, fr)] for l in lineas) <= N_MAX_ELEC, f"elec_{fr}"

    prob.solve(pulp.PULP_CBC_CMD(msg=0))
    estado = pulp.LpStatus[prob.status]

    filas = []
    for l in lineas:
        for fr in FRANJAS_DUR:
            f_val = int(round(fh[(l, fr)].value()))
            n_val = int(round(trains[(l, fr)].value()))
            head = round(60.0 / f_val, 1) if f_val > 0 else None
            f_via = 60.0 / HEADWAY_MIN[l]
            dem_link = round(peak_link.get((l, fr), 0.0))
            cap_ofrecida = f_val * CAP_AUTOMOTOR
            filas.append({
                "linea": l, "franja": fr,
                "demanda_punta_enlace_max": dem_link,
                "servicios_hora": f_val,
                "intervalo_min": head,
                "capacidad_hora": cap_ofrecida,
                "limitado_por_via_unica": bool(dem_link > f_via * CAP_AUTOMOTOR + 1),
                "trenes_uso": n_val,
                "ciclo_min": round(ciclo[l], 1),
            })
    df_fr = pd.DataFrame(filas)

    dem_tot = sum(dem.values())
    serv_tot = sum(v.value() for v in serv.values())
    flota_pico = int(df_fr.groupby("franja")["trenes_uso"].sum().max())
    resumen = {
        "estado": estado,
        "enfoque": "hora de diseno (punta) por franja",
        "peak_share": PEAK_SHARE,
        "demanda_punta_total": round(dem_tot),
        "demanda_punta_servida": round(serv_tot),
        "cobertura_pct": round(100 * serv_tot / dem_tot, 1),
        "flota_total": FLOTA,
        "flota_pico_usada": flota_pico,
        "flota_suficiente": bool(flota_pico <= FLOTA and round(100 * serv_tot / dem_tot, 1) >= 99.5),
        "limite_electrico_trenes": N_MAX_ELEC,
        "ciclo_min": {k: round(v, 1) for k, v in ciclo.items()},
        "oneway_min": oneway,
        "headway_min_via_unica": HEADWAY_MIN,
        "nota": ("Demanda de hora punta = demanda de franja * peak_share. Flota "
                 "dimensionada al pico. peak_share, headway de via unica y limite "
                 "electrico son supuestos; refinar con datos con marca de tiempo y "
                 "zonas SER desagregadas."),
    }
    return df_fr, resumen


def optimizar():
    od = pd.read_csv(CLEAN / "od_franjas.csv")
    itin = pd.read_csv(CLEAN / "itinerario_tiempos.csv")
    df_fr, resumen = _resolver(od, itin)
    resumen["sensibilidad_peak_share"] = sensibilidad_peak_share(od, itin)
    df_fr.to_csv(CLEAN / "optim_frecuencias.csv", index=False)
    with open(CLEAN / "optim_resumen.json", "w", encoding="utf-8") as fh_:
        json.dump(resumen, fh_, ensure_ascii=False, indent=2)
    return df_fr, resumen


if __name__ == "__main__":
    df_fr, res = optimizar()
    print("Optimizacion de capacidad y flota — HORA PUNTA (Etapa 2 refinada)")
    print("=" * 70)
    print(f"Estado: {res['estado']}  | Enfoque: {res['enfoque']}")
    print(f"peak_share por franja: {res['peak_share']}")
    print(f"Ciclo (min): L1={res['ciclo_min']['L1']}  L2={res['ciclo_min']['L2']}")
    print(f"Limite electrico: {res['limite_electrico_trenes']} trenes simultaneos\n")
    print(df_fr.to_string(index=False))
    print("\nDemanda hora punta total:   %d pax" % res["demanda_punta_total"])
    print("Demanda hora punta servida: %d pax (%.1f%%)" %
          (res["demanda_punta_servida"], res["cobertura_pct"]))
    print("Flota pico usada: %d / %d  -> flota suficiente: %s" %
          (res["flota_pico_usada"], res["flota_total"], res["flota_suficiente"]))
    print(f"\nGuardado: optim_frecuencias.csv, optim_resumen.json")
