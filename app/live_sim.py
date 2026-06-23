"""Vista 'Simulación en vivo' — fiel al modelo.

Los 16 automotores estan SIEMPRE visibles: en circulacion (sobre la via) o
estacionados en su cochera (disposicion inicial del grafico de rotaciones, pag. 16).
Muestra doble via (dos lineas) vs via unica (roja), señales (OpenTrack) y cocheras.
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
AZUL, ROJO, VERDE, NARANJA, GRIS = "#1F3864", "#C00000", "#2E7D32", "#FF8C00", "#666"


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
    for ln, lane in LANE.items():
        er = est_ref[ln]
        if er.empty:
            continue
        x0, x1 = er.dist_km.min(), er.dist_km.max()
        # DOBLE VIA: dos lineas paralelas
        for dy in (0.018, -0.018):
            base.append(go.Scatter(x=[x0, x1], y=[lane + dy, lane + dy], mode="lines",
                                   line=dict(color="#c2c2c2", width=1.6), hoverinfo="skip", showlegend=False))
        # VIA UNICA: una linea roja gruesa
        for lo, hi in _via_unica(ln):
            base.append(go.Scatter(x=[lo, hi], y=[lane, lane], mode="lines",
                                   line=dict(color=ROJO, width=5),
                                   hovertext=f"vía única {lo:.1f}–{hi:.1f} km", hoverinfo="text", showlegend=False))
        # estaciones
        base.append(go.Scatter(x=er.dist_km, y=[lane] * len(er), mode="markers",
                               marker=dict(symbol="line-ns-open", size=15, color="#888"),
                               hovertext=er.estacion, hoverinfo="text", showlegend=False))
        # señales
        sg = _senales(ln, _mt("infra_edges.csv"))
        if not sg.empty:
            sg = sg[(sg.km >= x0 - 0.2) & (sg.km <= x1 + 0.2)]
            pp, ds = sg[sg.principal], sg[~sg.principal]
            base.append(go.Scatter(x=pp.km, y=[lane + 0.07] * len(pp), mode="markers",
                                   marker=dict(symbol="triangle-up", size=6, color=VERDE),
                                   hovertext=pp.tipo, hoverinfo="text", showlegend=False))
            base.append(go.Scatter(x=ds.km, y=[lane + 0.07] * len(ds), mode="markers",
                                   marker=dict(symbol="triangle-down", size=5, color=NARANJA),
                                   hovertext=ds.tipo, hoverinfo="text", showlegend=False))
    # cocheras: marca + etiqueta de capacidad (infraestructura, estatica)
    for r in cocheras.itertuples():
        lane = LANE.get(r.linea, 0.0)
        base.append(go.Scatter(x=[r.km], y=[lane - 0.16], mode="markers+text",
                               marker=dict(symbol="square-open", size=16, color="#999"),
                               text=[r.codigo], textposition="bottom center", textfont=dict(size=8, color="#999"),
                               hovertext=f"Cochera {r.codigo} ({r.estacion}) cap {int(r.capacidad)}",
                               hoverinfo="text", showlegend=False))
    return base


def _trenes(df_t):
    tr = df_t[df_t.estado == "circulando"]
    xs, ys, txt, col = [], [], [], []
    for r in tr.itertuples():
        lane = LANE.get(r.tramo, 0.0)
        xs.append(r.dist_km); ys.append(lane + (0.10 if _ida(r.sentido) else -0.10))
        txt.append(f"{r.unidad} · serv {r.servicio} · {r.sentido} · km {r.dist_km}")
        col.append(AZUL if _ida(r.sentido) else ROJO)
    return go.Scatter(x=xs, y=ys, mode="markers", name="circulando",
                      marker=dict(size=13, color=col, line=dict(width=1, color="white")),
                      hovertext=txt, hoverinfo="text")


def _estacionados(df_t, cocheras):
    cap = {r.codigo: int(r.capacidad) for r in cocheras.itertuples()}
    es = df_t[df_t.estado == "cochera"].copy()
    xs, ys, txt, col = [], [], [], []
    for code, g in es.groupby("cochera"):
        units = list(g.unidad)
        km = g.dist_km.iloc[0]
        if pd.isna(km):
            continue
        lane = LANE.get(g.tramo.iloc[0], 0.0) if g.tramo.iloc[0] in LANE else (1.0 if km <= 28 else 0.0)
        sobre = len(units) > cap.get(code, 99)
        for i, u in enumerate(sorted(units)):
            xs.append(km); ys.append(lane - 0.26 - 0.055 * i)
            txt.append(f"{u} estacionado en cochera {code} ({len(units)}/{cap.get(code,'?')})")
            col.append(ROJO if sobre else "#444")
    return go.Scatter(x=xs, y=ys, mode="markers", name="en cochera",
                      marker=dict(size=10, color=col, symbol="circle", line=dict(width=1, color="white")),
                      hovertext=txt, hoverinfo="text")


def _layout(fig, titulo=None):
    fig.update_layout(height=600, margin=dict(l=10, r=10, t=40 if titulo else 24, b=10), title=titulo,
                      yaxis=dict(tickvals=[1, 0], ticktext=["L2", "L1"], range=[-0.85, 1.35]),
                      xaxis=dict(title="km", showgrid=True, gridcolor="#f4f4f4"), showlegend=False)


def render():
    st.subheader("Simulación en vivo — los 16 automotores, siempre visibles (Lun-Vie)")
    st.caption("Fiel al modelo: posición desde la rotación real; disposición inicial del gráfico "
               "de rotaciones (pág. 16). Dos líneas grises = doble vía; línea roja = vía única; "
               "▲ verde/▽ naranja = señales; cuadros = cocheras (código y capacidad). Puntos azul/rojo "
               "= tren circulando (ida/vuelta); puntos oscuros bajo cada cochera = automotores estacionados "
               "(rojo si excede capacidad).")
    grid = _load("estado_grilla.csv", _mt("estado_grilla.csv"))
    cocheras = _load("cocheras.csv", _mt("cocheras.csv"))
    est_ref = _ref()
    if grid.empty or cocheras.empty:
        st.info("Falta estado_grilla.csv o cocheras.csv. Corre run_all.py.")
        return

    tiempos = sorted(grid.t_s.unique())
    base = _base(est_ref, cocheras)
    nb = len(base)
    g0 = grid[grid.t_s == tiempos[0]]
    fig = go.Figure(data=base + [_trenes(g0), _estacionados(g0, cocheras)])
    frames = []
    for ts in tiempos:
        gt = grid[grid.t_s == ts]
        frames.append(go.Frame(data=[_trenes(gt), _estacionados(gt, cocheras)],
                               traces=[nb, nb + 1], name=_hhmmss(ts)[:5]))
    fig.frames = frames
    pasos = [dict(method="animate", label=_hhmmss(ts)[:5],
                  args=[[_hhmmss(ts)[:5]], dict(mode="immediate", frame=dict(duration=0, redraw=True),
                        transition=dict(duration=0))]) for ts in tiempos]
    fig.update_layout(
        updatemenus=[dict(type="buttons", showactive=False, x=0.0, y=1.16, xanchor="left", buttons=[
            dict(label="▶ Reproducir", method="animate",
                 args=[None, dict(frame=dict(duration=140, redraw=True), fromcurrent=True, transition=dict(duration=0))]),
            dict(label="⏸ Pausa", method="animate",
                 args=[[None], dict(mode="immediate", frame=dict(duration=0, redraw=False))])])],
        sliders=[dict(active=0, x=0.08, len=0.9, currentvalue=dict(prefix="Hora: "), steps=pasos)])
    _layout(fig)
    st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.markdown("**Instante exacto** — ingresa una hora y mira el estado en ese segundo:")
    c1, c2, c3 = st.columns(3)
    hh, mm, ss = c1.number_input("Hora", 0, 23, 5), c2.number_input("Minuto", 0, 59, 0), c3.number_input("Segundo", 0, 59, 0)
    try:
        import estado_dia
        unidades, _ = estado_dia.cargar()
        estd = estado_dia.estado(hh * 60 + mm + ss / 60.0, unidades)
        rows = [{"estado": "circulando", "unidad": x["unidad"], "servicio": x["servicio"],
                 "tramo": x["tramo"], "sentido": x["sentido"], "dist_km": x["dist_km"], "cochera": ""} for x in estd["trenes"]]
        rows += [{"estado": "cochera", "unidad": e["unidad"], "servicio": "", "tramo": e["linea"],
                  "sentido": "", "dist_km": e["dist_km"], "cochera": e["cochera"]} for e in estd["estacionados"]]
        df_t = pd.DataFrame(rows)
        fig2 = go.Figure(data=_base(est_ref, cocheras) + [_trenes(df_t), _estacionados(df_t, cocheras)])
        _layout(fig2, titulo=f"Estado a las {hh:02d}:{mm:02d}:{ss:02d}")
        st.plotly_chart(fig2, use_container_width=True)
        a, b = st.columns(2)
        a.metric("Circulando", len(estd["trenes"]))
        b.metric("En cochera", len(estd["estacionados"]))
        a.dataframe(pd.DataFrame(estd["trenes"]), use_container_width=True, hide_index=True)
        from collections import defaultdict
        occ = defaultdict(list)
        for e in estd["estacionados"]:
            occ[e["cochera"]].append(e["unidad"])
        cap = {r.codigo: int(r.capacidad) for r in cocheras.itertuples()}
        b.dataframe(pd.DataFrame([{"cochera": c, "ocup/cap": f"{len(u)}/{cap.get(c,'?')}",
                                   "automotores": ", ".join(sorted(u))} for c, u in sorted(occ.items())]),
                    use_container_width=True, hide_index=True)
    except Exception as e:
        st.warning(f"No se pudo calcular el instante exacto: {e}")
