"""Vista 'Simulación en vivo' — fiel al modelo, con operación por vía en L2.

L2 se dibuja con sus DOS vías físicas (Principal oriente/poniente) donde hay doble
vía y una sola donde hay vía única (clasificacion desde OpenTrack). Los trenes
circulan por la vía DERECHA segun el sentido (sur=poniente, norte=oriente) y se
resalta el CANTON que ocupa cada tren. Los enlaces (agujas) se marcan entre vías.
L1 se muestra en un carril simple (ida/vuelta). Los 16 automotores estan SIEMPRE
visibles (en cochera cuando no circulan). Disposicion inicial: grafico pag. 16.
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

AZUL, ROJO, VERDE, NARANJA = "#1F3864", "#C00000", "#2E7D32", "#FF8C00"
PON_Y, ORI_Y, SIN_Y = 1.12, 0.92, 1.02     # vías L2 (poniente arriba, oriente abajo)
L1_Y = 0.0
COCH_Y = {"L2": 0.72, "L1": -0.22}


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


def _ida(s):
    return ("->CW" in s) or ("->LJ" in s)


def _tramos_l2():
    tv = _load("tramos_via.csv", _mt("tramos_via.csv"))
    return tv[tv.linea == "L2"] if not tv.empty else pd.DataFrame()


def _y_l2(km, sentido, tramos):
    """vía (y) de un tren L2 segun su km y sentido (vía derecha)."""
    row = tramos[(tramos.km_lo <= km) & (tramos.km_hi >= km)]
    if len(row):
        r = row.iloc[0]
        if r.tipo == "doble":
            return PON_Y if _ida(sentido) else ORI_Y     # sur=poniente, norte=oriente
        if "oriente" in r.vias:
            return ORI_Y
        if "poniente" in r.vias:
            return PON_Y
    return SIN_Y


def _canton(km, bl):
    for r in bl.itertuples():
        if r.dist_lo - 1e-6 <= km <= r.dist_hi + 1e-6:
            return (r.dist_lo, r.dist_hi)
    return None


def _base(est_ref, cocheras, tramos, enlaces, bl2):
    base = []
    # --- L2: dos vías físicas ---
    for r in tramos.itertuples():
        if "poniente" in r.vias:
            base.append(go.Scatter(x=[r.km_lo, r.km_hi], y=[PON_Y, PON_Y], mode="lines",
                                   line=dict(color="#777", width=2.2), hoverinfo="skip", showlegend=False))
        if "oriente" in r.vias:
            base.append(go.Scatter(x=[r.km_lo, r.km_hi], y=[ORI_Y, ORI_Y], mode="lines",
                                   line=dict(color="#777", width=2.2), hoverinfo="skip", showlegend=False))
        if r.tipo == "no determinado":
            base.append(go.Scatter(x=[r.km_lo, r.km_hi], y=[SIN_Y, SIN_Y], mode="lines",
                                   line=dict(color="#bbb", width=1.5, dash="dash"),
                                   hovertext="sin doble vía registrada", hoverinfo="text", showlegend=False))
    # enlaces (agujas) L2: conector entre vías
    ex, ey = [], []
    for k in enlaces.km:
        ex += [k, k + 0.25, None]; ey += [ORI_Y, PON_Y, None]
    if ex:
        base.append(go.Scatter(x=ex, y=ey, mode="lines", line=dict(color=VERDE, width=0.7),
                               hoverinfo="skip", showlegend=False))
    # estaciones y señales L2
    er = est_ref["L2"]
    if not er.empty:
        base.append(go.Scatter(x=er.dist_km, y=[SIN_Y] * len(er), mode="markers",
                               marker=dict(symbol="line-ns-open", size=22, color="#aaa"),
                               hovertext=er.estacion, hoverinfo="text", showlegend=False))
    sg = _senales("L2", _mt("infra_edges.csv"))
    if not sg.empty:
        sg = sg[(sg.km >= 0) & (sg.km <= 28)]
        pp = sg[sg.principal]
        base.append(go.Scatter(x=pp.km, y=[PON_Y + 0.05] * len(pp), mode="markers",
                               marker=dict(symbol="triangle-up", size=6, color=VERDE),
                               hovertext=pp.tipo, hoverinfo="text", showlegend=False))
    # --- L1: carril simple ---
    er1 = est_ref["L1"]
    if not er1.empty:
        base.append(go.Scatter(x=[er1.dist_km.min(), er1.dist_km.max()], y=[L1_Y, L1_Y], mode="lines",
                               line=dict(color="#999", width=2.2), hoverinfo="skip", showlegend=False))
        base.append(go.Scatter(x=er1.dist_km, y=[L1_Y] * len(er1), mode="markers",
                               marker=dict(symbol="line-ns-open", size=15, color="#aaa"),
                               hovertext=er1.estacion, hoverinfo="text", showlegend=False))
        try:
            from via_unica import VIA_UNICA
            for n, lo, hi, bq in VIA_UNICA.get("L1", []):
                if bq:
                    base.append(go.Scatter(x=[lo, hi], y=[L1_Y, L1_Y], mode="lines",
                                           line=dict(color=ROJO, width=4), hovertext=f"vía única {n}",
                                           hoverinfo="text", showlegend=False))
        except Exception:
            pass
    # cocheras (cuadros con codigo y capacidad)
    for r in cocheras.itertuples():
        y = COCH_Y.get(r.linea, -0.22)
        base.append(go.Scatter(x=[r.km], y=[y], mode="markers+text",
                               marker=dict(symbol="square-open", size=15, color="#999"),
                               text=[r.codigo], textposition="bottom center", textfont=dict(size=7, color="#999"),
                               hovertext=f"Cochera {r.codigo} ({r.estacion}) cap {int(r.capacidad)}",
                               hoverinfo="text", showlegend=False))
    return base


def _dyn(df_t, tramos, bl2, cocheras):
    """traces dinamicas: trenes, cantones ocupados (L2), estacionados."""
    cap = {r.codigo: int(r.capacidad) for r in cocheras.itertuples()}
    coch_y = {r.codigo: COCH_Y.get(r.linea, -0.22) for r in cocheras.itertuples()}
    tx, ty, ttxt, tcol = [], [], [], []
    cx, cy = [], []      # cantones ocupados (segmentos)
    run = df_t[df_t.estado == "circulando"]
    for r in run.itertuples():
        ida = _ida(r.sentido)
        if r.tramo == "L2":
            y = _y_l2(r.dist_km, r.sentido, tramos)
            ct = _canton(r.dist_km, bl2)
            if ct:
                cx += [ct[0], ct[1], None]; cy += [y, y, None]
        else:
            y = L1_Y + (0.09 if ida else -0.09)
        tx.append(r.dist_km); ty.append(y)
        ttxt.append(f"{r.unidad} · serv {r.servicio} · {r.sentido} · km {r.dist_km}")
        tcol.append(AZUL if ida else ROJO)
    trenes = go.Scatter(x=tx, y=ty, mode="markers", name="circulando",
                        marker=dict(size=12, color=tcol, line=dict(width=1, color="white")),
                        hovertext=ttxt, hoverinfo="text")
    cantones = go.Scatter(x=cx, y=cy, mode="lines", name="cantón ocupado",
                          line=dict(color="rgba(192,0,0,0.28)", width=8), hoverinfo="skip")
    # estacionados
    es = df_t[df_t.estado == "cochera"]
    ex, ey, etxt, ecol = [], [], [], []
    for code, g in es.groupby("cochera"):
        units = sorted(g.unidad)
        km = g.dist_km.iloc[0]
        if pd.isna(km):
            continue
        y0 = coch_y.get(code, -0.22)
        sobre = len(units) > cap.get(code, 99)
        for i, u in enumerate(units):
            ex.append(km); ey.append(y0 - 0.05 - 0.05 * i)
            etxt.append(f"{u} en cochera {code} ({len(units)}/{cap.get(code,'?')})")
            ecol.append(ROJO if sobre else "#444")
    estac = go.Scatter(x=ex, y=ey, mode="markers", name="en cochera",
                       marker=dict(size=9, color=ecol, line=dict(width=1, color="white")),
                       hovertext=etxt, hoverinfo="text")
    return [trenes, cantones, estac]


def _layout(fig, titulo=None):
    fig.update_layout(height=620, margin=dict(l=10, r=10, t=42 if titulo else 26, b=10), title=titulo,
                      yaxis=dict(tickvals=[PON_Y, ORI_Y, L1_Y], ticktext=["L2 pon.", "L2 ori.", "L1"],
                                 range=[-0.75, 1.32]),
                      xaxis=dict(title="km", showgrid=True, gridcolor="#f4f4f4"), showlegend=False)


def render():
    st.subheader("Simulación en vivo — operación por vía (L2 con vía derecha y enlaces)")
    st.caption("Fiel al modelo. L2: dos vías físicas (Principal poniente arriba / oriente abajo); "
               "los trenes circulan por la vía DERECHA según el sentido (sur→poniente, norte→oriente) "
               "y se resalta el cantón ocupado (barra roja). Verde = enlaces (agujas) reales; línea "
               "punteada = tramo sin doble vía registrada. L1 en carril simple. Cuadros = cocheras.")
    grid = _load("estado_grilla.csv", _mt("estado_grilla.csv"))
    cocheras = _load("cocheras.csv", _mt("cocheras.csv"))
    tramos = _tramos_l2()
    enlaces = _load("enlaces.csv", _mt("enlaces.csv"))
    enlaces = enlaces[(enlaces.linea == "L2") & (enlaces.km <= 28)] if not enlaces.empty else pd.DataFrame({"km": []})
    bl = _load("bloques.csv", _mt("bloques.csv"))
    bl2 = bl[bl.linea == "L2"] if not bl.empty else pd.DataFrame(columns=["dist_lo", "dist_hi"])
    est_ref = _ref()
    if grid.empty or cocheras.empty or tramos.empty:
        st.info("Faltan datos (estado_grilla / cocheras / tramos_via). Corre run_all.py.")
        return

    tiempos = sorted(grid.t_s.unique())
    base = _base(est_ref, cocheras, tramos, enlaces, bl2)
    nb = len(base)
    g0 = grid[grid.t_s == tiempos[0]]
    fig = go.Figure(data=base + _dyn(g0, tramos, bl2, cocheras))
    frames = []
    for ts in tiempos:
        frames.append(go.Frame(data=_dyn(grid[grid.t_s == ts], tramos, bl2, cocheras),
                               traces=[nb, nb + 1, nb + 2], name=_hhmmss(ts)[:5]))
    fig.frames = frames
    pasos = [dict(method="animate", label=_hhmmss(ts)[:5],
                  args=[[_hhmmss(ts)[:5]], dict(mode="immediate", frame=dict(duration=0, redraw=True),
                        transition=dict(duration=0))]) for ts in tiempos]
    fig.update_layout(
        updatemenus=[dict(type="buttons", showactive=False, x=0.0, y=1.14, xanchor="left", buttons=[
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
    hh, mm, ss = c1.number_input("Hora", 0, 23, 7), c2.number_input("Minuto", 0, 59, 35), c3.number_input("Segundo", 0, 59, 0)
    try:
        import estado_dia
        unidades, _ = estado_dia.cargar()
        estd = estado_dia.estado(hh * 60 + mm + ss / 60.0, unidades)
        rows = [{"estado": "circulando", "unidad": x["unidad"], "servicio": x["servicio"], "tramo": x["tramo"],
                 "sentido": x["sentido"], "dist_km": x["dist_km"], "cochera": ""} for x in estd["trenes"]]
        rows += [{"estado": "cochera", "unidad": e["unidad"], "servicio": "", "tramo": e["linea"],
                  "sentido": "", "dist_km": e["dist_km"], "cochera": e["cochera"]} for e in estd["estacionados"]]
        df_t = pd.DataFrame(rows)
        fig2 = go.Figure(data=_base(est_ref, cocheras, tramos, enlaces, bl2) + _dyn(df_t, tramos, bl2, cocheras))
        _layout(fig2, titulo=f"Estado a las {hh:02d}:{mm:02d}:{ss:02d}")
        st.plotly_chart(fig2, use_container_width=True)
        # tabla: tren, vía y cantón ocupado (L2)
        filas = []
        for x in estd["trenes"]:
            via = ""
            if x["tramo"] == "L2":
                y = _y_l2(x["dist_km"], x["sentido"], tramos)
                via = "poniente" if y == PON_Y else ("oriente" if y == ORI_Y else "única/n.d.")
                ct = _canton(x["dist_km"], bl2)
                via += f" · cantón {ct[0]:.1f}–{ct[1]:.1f} km" if ct else ""
            filas.append({"unidad": x["unidad"], "servicio": x["servicio"], "línea": x["tramo"],
                          "sentido": x["sentido"], "km": x["dist_km"], "vía / cantón": via})
        st.markdown("**Trenes circulando — vía y cantón ocupado**")
        st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)
    except Exception as e:
        st.warning(f"No se pudo calcular el instante exacto: {e}")
