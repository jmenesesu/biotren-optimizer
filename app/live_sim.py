"""Vista 'Simulación en vivo': trenes, señales, vías y cocheras (situación actual).

Reconstruye desde la rotación de los 16 automotores (horarios_limpios) la posición
de cada tren en cualquier instante, sobre un esquema con la infraestructura real:
estaciones, señales (OpenTrack), tramos de vía única y cocheras (con capacidad).
"""
import sys
from pathlib import Path
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

REPO = Path(__file__).resolve().parents[1]
CLEAN = REPO / "datos" / "clean"
for p in ["parsers", "optimizador", "simulador"]:
    sys.path.append(str(REPO / p))

LANE = {"L2": 1.0, "L1": 0.0}
AZUL, ROJO, VERDE, NARANJA = "#1F3864", "#C00000", "#2E7D32", "#FF8C00"


def _hhmmss(s):
    s = int(s)
    return f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}"


@st.cache_data
def _load(nombre, _mt):
    f = CLEAN / nombre
    return pd.read_csv(f) if f.exists() else pd.DataFrame()


def _mt(nombre):
    f = CLEAN / nombre
    return f.stat().st_mtime if f.exists() else 0.0


@st.cache_data
def _senales(linea, _mt):
    import estaciones_maestro as em
    return em.senales_km(linea)


def _ref():
    r = _load("malla_real.csv", _mt("malla_real.csv"))
    out = {}
    for ln in ["L2", "L1"]:
        out[ln] = (r[r.linea == ln][["estacion", "dist_km"]].drop_duplicates()
                   .sort_values("dist_km").reset_index(drop=True)) if not r.empty else pd.DataFrame(columns=["estacion", "dist_km"])
    return out


def _ida(sentido):
    return ("->CW" in sentido) or ("->LJ" in sentido)


def _via_unica(linea):
    try:
        from via_unica import VIA_UNICA
        return [(lo, hi) for n, lo, hi, bq in VIA_UNICA.get(linea, []) if bq]
    except Exception:
        return []


def _base(est_ref, cocheras):
    base = []
    rango = {}
    for ln, lane in LANE.items():
        er = est_ref[ln]
        if er.empty:
            continue
        x0, x1 = er.dist_km.min(), er.dist_km.max()
        rango[ln] = (x0, x1)
        # vía doble: línea base; vía única: segmento rojo grueso encima
        base.append(go.Scatter(x=[x0, x1], y=[lane, lane], mode="lines",
                               line=dict(color="#cfcfcf", width=3), hoverinfo="skip", showlegend=False))
        for lo, hi in _via_unica(ln):
            base.append(go.Scatter(x=[lo, hi], y=[lane, lane], mode="lines",
                                   line=dict(color="#C00000", width=6),
                                   hovertext=f"vía única {lo:.1f}–{hi:.1f} km", hoverinfo="text", showlegend=False))
        # estaciones
        base.append(go.Scatter(x=er.dist_km, y=[lane] * len(er), mode="markers",
                               marker=dict(symbol="line-ns-open", size=14, color="#888"),
                               hovertext=er.estacion, hoverinfo="text", showlegend=False))
        # señales
        sg = _senales(ln, _mt("infra_edges.csv"))
        if not sg.empty:
            sg = sg[(sg.km >= x0 - 0.2) & (sg.km <= x1 + 0.2)]
            pp = sg[sg.principal]; ds = sg[~sg.principal]
            base.append(go.Scatter(x=pp.km, y=[lane + 0.06] * len(pp), mode="markers",
                                   marker=dict(symbol="triangle-up", size=7, color=VERDE),
                                   hovertext=pp.tipo, hoverinfo="text", showlegend=False))
            base.append(go.Scatter(x=ds.km, y=[lane + 0.06] * len(ds), mode="markers",
                                   marker=dict(symbol="triangle-down", size=6, color=NARANJA),
                                   hovertext=ds.tipo, hoverinfo="text", showlegend=False))
    return base


def _trenes(df_t):
    tr = df_t[df_t.estado == "circulando"]
    xs, ys, txt, col = [], [], [], []
    for r in tr.itertuples():
        lane = LANE.get(r.tramo, 0.0)
        xs.append(r.dist_km); ys.append(lane + (0.12 if _ida(r.sentido) else -0.12))
        txt.append(f"{r.unidad} · serv {r.servicio} · {r.sentido} · km {r.dist_km}")
        col.append(AZUL if _ida(r.sentido) else ROJO)
    return go.Scatter(x=xs, y=ys, mode="markers", name="trenes",
                      marker=dict(size=13, color=col, line=dict(width=1, color="white")),
                      hovertext=txt, hoverinfo="text")


def _cocheras_trace(df_t, cocheras, lay):
    from collections import defaultdict
    occ = defaultdict(list)
    coch = df_t[df_t.estado.astype(str).str.startswith("cochera:")]
    for r in coch.itertuples():
        code = lay.get(r.estado.split(":", 1)[1])
        if code:
            occ[code].append(r.unidad)
    xs, ys, txt, col, sz = [], [], [], [], []
    for r in cocheras.itertuples():
        lane = LANE.get(r.linea, 0.0)
        us = sorted(occ.get(r.codigo, []))
        n, cap = len(us), int(r.capacidad)
        xs.append(r.km); ys.append(lane - 0.36)
        txt.append(f"Cochera {r.codigo} ({r.estacion}) {n}/{cap}" + (f" → {', '.join(us)}" if us else " (vacía)"))
        col.append("#C00000" if n > cap else (VERDE if n > 0 else "#d9d9d9"))
        sz.append(16 + 5 * n)
    return go.Scatter(x=xs, y=ys, mode="markers+text", name="cocheras",
                      marker=dict(size=sz, color=col, opacity=0.55, symbol="square",
                                  line=dict(width=1, color="#555")),
                      text=[f"{len(occ.get(r.codigo, []))}/{int(r.capacidad)}" for r in cocheras.itertuples()],
                      textposition="middle center", textfont=dict(size=8, color="black"),
                      hovertext=txt, hoverinfo="text")


def _layout(fig, titulo=None):
    fig.update_layout(
        height=560, margin=dict(l=10, r=10, t=40 if titulo else 24, b=10), title=titulo,
        yaxis=dict(tickvals=[1, 0], ticktext=["L2", "L1"], range=[-0.7, 1.35]),
        xaxis=dict(title="km", showgrid=True, gridcolor="#f4f4f4"), showlegend=False)


def render():
    st.subheader("Simulación en vivo — trenes, señales, vías y cocheras (Lun-Vie)")
    st.caption("Desde la rotación de los 16 automotores. L2 arriba, L1 abajo. Azul = sentido "
               "Concepción→Coronel / Mercado→Laja, rojo = inverso. Línea roja gruesa = vía única; "
               "triángulos verdes = señales principales, naranjos = distantes; cuadros = cocheras "
               "(número = ocupados/capacidad; rojo = sobrecupo).")
    grid = _load("estado_grilla.csv", _mt("estado_grilla.csv"))
    cocheras = _load("cocheras.csv", _mt("cocheras.csv"))
    est_ref = _ref()
    if grid.empty or cocheras.empty:
        st.info("Falta estado_grilla.csv o cocheras.csv. Corre run_all.py.")
        return
    try:
        import cocheras as cmod
        lay = cmod.LAYOVER_A_COCHERA
    except Exception:
        lay = {}

    tiempos = sorted(grid.t_s.unique())
    base = _base(est_ref, cocheras)
    nb = len(base)
    g0 = grid[grid.t_s == tiempos[0]]
    fig = go.Figure(data=base + [_trenes(g0), _cocheras_trace(g0, cocheras, lay)])
    frames = []
    for ts in tiempos:
        gt = grid[grid.t_s == ts]
        frames.append(go.Frame(data=[_trenes(gt), _cocheras_trace(gt, cocheras, lay)],
                               traces=[nb, nb + 1], name=_hhmmss(ts)[:5]))
    fig.frames = frames
    pasos = [dict(method="animate", label=_hhmmss(ts)[:5],
                  args=[[_hhmmss(ts)[:5]], dict(mode="immediate", frame=dict(duration=0, redraw=True),
                        transition=dict(duration=0))]) for ts in tiempos]
    fig.update_layout(
        updatemenus=[dict(type="buttons", showactive=False, x=0.0, y=1.16, xanchor="left", buttons=[
            dict(label="▶ Reproducir", method="animate",
                 args=[None, dict(frame=dict(duration=120, redraw=True), fromcurrent=True, transition=dict(duration=0))]),
            dict(label="⏸ Pausa", method="animate",
                 args=[[None], dict(mode="immediate", frame=dict(duration=0, redraw=False))])])],
        sliders=[dict(active=0, x=0.08, len=0.9, currentvalue=dict(prefix="Hora: "), steps=pasos)])
    _layout(fig)
    st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.markdown("**Instante exacto** — ingresa una hora y mira el estado en ese segundo:")
    c1, c2, c3 = st.columns(3)
    hh, mm, ss = c1.number_input("Hora", 0, 23, 7), c2.number_input("Minuto", 0, 59, 30), c3.number_input("Segundo", 0, 59, 0)
    try:
        import estado_dia
        unidades, _ = estado_dia.cargar()
        t = hh * 60 + mm + ss / 60.0
        estd = estado_dia.estado(t, unidades)
        df_t = pd.DataFrame(
            [{"estado": "circulando", "unidad": x["unidad"], "servicio": x["servicio"],
              "tramo": x["tramo"], "sentido": x["sentido"], "dist_km": x["dist_km"]} for x in estd["trenes"]] +
            [{"estado": f"cochera:{e}", "unidad": u, "servicio": "", "tramo": "", "sentido": "", "dist_km": None}
             for e, us in estd["cocheras"].items() for u in us])
        fig2 = go.Figure(data=_base(est_ref, cocheras) + [_trenes(df_t), _cocheras_trace(df_t, cocheras, lay)])
        _layout(fig2, titulo=f"Estado a las {hh:02d}:{mm:02d}:{ss:02d}")
        st.plotly_chart(fig2, use_container_width=True)
        a, b = st.columns(2)
        a.metric("Trenes circulando", len(estd["trenes"]))
        b.metric("Automotores en cochera", sum(len(v) for v in estd["cocheras"].values()))
        a.dataframe(pd.DataFrame(estd["trenes"]), use_container_width=True, hide_index=True)
        from collections import defaultdict
        occ = defaultdict(list)
        for e, us in estd["cocheras"].items():
            code = lay.get(e, e)
            occ[code] += us
        filas = []
        for r in cocheras.itertuples():
            us = sorted(occ.get(r.codigo, []))
            filas.append({"cochera": r.codigo, "estación": r.estacion, "ocup/cap": f"{len(us)}/{r.capacidad}",
                          "automotores": ", ".join(us)})
        b.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)
    except Exception as e:
        st.warning(f"No se pudo calcular el instante exacto: {e}")
