"""Vista 'Simulación en vivo' — fiel al modelo, una línea a ancho completo.

Selector de línea (L2 / L1). L2 se dibuja con sus DOS vías físicas (Principal
oriente/poniente) donde hay doble vía y una sola en vía única; los trenes circulan
por la vía DERECHA según el sentido (sur=poniente, norte=oriente) y se resalta el
cantón ocupado. Enlaces (agujas) reales entre vías. L1 en carril simple. Los 16
automotores están SIEMPRE visibles (en cochera cuando no circulan). Disposición
inicial y de fin de día del gráfico de rotaciones (pág. 16).
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
# geometría vertical (normalizada 0..1) por línea
GEO = {
    "L2": dict(pon=0.82, ori=0.60, sin=0.71, lane=None, coch=0.34, xmax=28.5),
    "L1": dict(pon=None, ori=None, sin=None, lane=0.66, coch=0.34, xmax=86.0),
}


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


def _ref(linea):
    r = _load("malla_real.csv", _mt("malla_real.csv"))
    if r.empty:
        return pd.DataFrame(columns=["estacion", "dist_km"])
    return (r[r.linea == linea][["estacion", "dist_km"]].drop_duplicates()
            .sort_values("dist_km").reset_index(drop=True))


def _ida(s):
    return ("->CW" in s) or ("->LJ" in s)


def _tramos(linea):
    tv = _load("tramos_via.csv", _mt("tramos_via.csv"))
    return tv[tv.linea == linea] if not tv.empty else pd.DataFrame()


def _y_via(km, sentido, tramos, g):
    """y de un tren según km/sentido (vía derecha) en L2; en L1 = carril."""
    if g["lane"] is not None:
        return g["lane"] + (0.06 if _ida(sentido) else -0.06)
    row = tramos[(tramos.km_lo <= km) & (tramos.km_hi >= km)]
    if len(row) and row.iloc[0].tipo == "doble":
        return g["pon"] if _ida(sentido) else g["ori"]
    return g["sin"]


def _canton(km, bl):
    for r in bl.itertuples():
        if r.dist_lo - 1e-6 <= km <= r.dist_hi + 1e-6:
            return (r.dist_lo, r.dist_hi)
    return None


def _base(linea, est_ref, cocheras, tramos, enlaces, g):
    base = []
    if g["lane"] is None:   # L2 dos vías
        for r in tramos.itertuples():
            if r.tipo == "doble":
                for y in (g["pon"], g["ori"]):
                    base.append(go.Scatter(x=[r.km_lo, r.km_hi], y=[y, y], mode="lines",
                                           line=dict(color="#777", width=2.4), hoverinfo="skip", showlegend=False))
            else:
                base.append(go.Scatter(x=[r.km_lo, r.km_hi], y=[g["sin"], g["sin"]], mode="lines",
                                       line=dict(color=ROJO, width=3.5),
                                       hovertext=f"vía única {r.km_lo:.1f}–{r.km_hi:.1f}", hoverinfo="text", showlegend=False))
        ex, ey = [], []
        for k in enlaces.km:
            ex += [k, k + 0.18, None]; ey += [g["ori"], g["pon"], None]
        if ex:
            base.append(go.Scatter(x=ex, y=ey, mode="lines", line=dict(color=VERDE, width=0.8),
                                   hoverinfo="skip", showlegend=False))
        sy = g["sin"]
    else:                   # L1 carril simple
        if not est_ref.empty:
            base.append(go.Scatter(x=[est_ref.dist_km.min(), est_ref.dist_km.max()], y=[g["lane"], g["lane"]],
                                   mode="lines", line=dict(color="#888", width=2.4), hoverinfo="skip", showlegend=False))
        try:
            from via_unica import VIA_UNICA
            for n, lo, hi, bq in VIA_UNICA.get("L1", []):
                if bq:
                    base.append(go.Scatter(x=[lo, hi], y=[g["lane"], g["lane"]], mode="lines",
                                           line=dict(color=ROJO, width=4), hovertext=f"vía única {n}",
                                           hoverinfo="text", showlegend=False))
        except Exception:
            pass
        sy = g["lane"]
    # estaciones (etiqueta) y señales
    if not est_ref.empty:
        base.append(go.Scatter(x=est_ref.dist_km, y=[sy] * len(est_ref), mode="markers+text",
                               marker=dict(symbol="line-ns-open", size=26, color="#aaa"),
                               text=est_ref.estacion, textposition="top center", textfont=dict(size=8, color="#777"),
                               hovertext=est_ref.estacion, hoverinfo="text", showlegend=False))
    sg = _senales(linea, _mt("infra_edges.csv"))
    if not sg.empty:
        sg = sg[(sg.km >= 0) & (sg.km <= g["xmax"])]
        pp = sg[sg.principal]
        ytop = (g["pon"] if g["lane"] is None else g["lane"]) + 0.05
        base.append(go.Scatter(x=pp.km, y=[ytop] * len(pp), mode="markers",
                               marker=dict(symbol="triangle-up", size=6, color=VERDE),
                               hovertext=pp.tipo, hoverinfo="text", showlegend=False))
    for r in cocheras.itertuples():
        base.append(go.Scatter(x=[r.km], y=[g["coch"]], mode="markers+text",
                               marker=dict(symbol="square-open", size=16, color="#999"),
                               text=[r.codigo], textposition="bottom center", textfont=dict(size=8, color="#999"),
                               hovertext=f"Cochera {r.codigo} ({r.estacion}) cap {int(r.capacidad)}",
                               hoverinfo="text", showlegend=False))
    return base


def _dyn(df_t, linea, tramos, bl, cocheras, g):
    cap = {r.codigo: int(r.capacidad) for r in cocheras.itertuples()}
    tx, ty, ttxt, tcol, cx, cy = [], [], [], [], [], []
    run = df_t[df_t.estado == "circulando"]
    for r in run.itertuples():
        y = _y_via(r.dist_km, r.sentido, tramos, g)
        if g["lane"] is None:
            ct = _canton(r.dist_km, bl)
            if ct:
                cx += [ct[0], ct[1], None]; cy += [y, y, None]
        tx.append(r.dist_km); ty.append(y)
        ttxt.append(f"{r.unidad} · serv {r.servicio} · {r.sentido} · km {r.dist_km}")
        tcol.append(AZUL if _ida(r.sentido) else ROJO)
    trenes = go.Scatter(x=tx, y=ty, mode="markers", name="circulando",
                        marker=dict(size=14, color=tcol, line=dict(width=1, color="white")),
                        hovertext=ttxt, hoverinfo="text")
    cantones = go.Scatter(x=cx, y=cy, mode="lines", line=dict(color="rgba(192,0,0,0.28)", width=9), hoverinfo="skip")
    es = df_t[df_t.estado == "cochera"]
    ex, ey, etxt, ecol = [], [], [], []
    for code, gg in es.groupby("cochera"):
        units = sorted(gg.unidad); km = gg.dist_km.iloc[0]
        if pd.isna(km):
            continue
        sobre = len(units) > cap.get(code, 99)
        for i, u in enumerate(units):
            ex.append(km); ey.append(g["coch"] - 0.05 - 0.045 * i)
            etxt.append(f"{u} en cochera {code} ({len(units)}/{cap.get(code,'?')})")
            ecol.append(ROJO if sobre else "#444")
    estac = go.Scatter(x=ex, y=ey, mode="markers", name="en cochera",
                       marker=dict(size=10, color=ecol, line=dict(width=1, color="white")),
                       hovertext=etxt, hoverinfo="text")
    return [trenes, cantones, estac]


def _fig(linea, df0_or_grid, est_ref, cocheras, tramos, enlaces, bl, g, animar=None):
    base = _base(linea, est_ref, cocheras, tramos, enlaces, g)
    fig = go.Figure(data=base + _dyn(df0_or_grid, linea, tramos, bl, cocheras, g))
    fig.update_layout(height=560, margin=dict(l=10, r=10, t=30, b=10),
                      yaxis=dict(visible=False, range=[0.0, 1.02]),
                      xaxis=dict(title="km", range=[-0.5, g["xmax"]], showgrid=True, gridcolor="#f4f4f4"),
                      showlegend=False)
    return fig, len(base)


def render():
    st.subheader("Simulación en vivo — operación por vía (los 16 automotores siempre visibles)")
    linea = st.radio("Línea", ["L2", "L1"], horizontal=True, key="sim_linea")
    if linea == "L2":
        st.caption("L2 a ancho completo. Dos vías físicas (Principal poniente arriba / oriente abajo); "
                   "los trenes circulan por la vía DERECHA (sur→poniente, norte→oriente) y se resalta el "
                   "cantón ocupado (rojo). Verde = enlaces (agujas) reales; rojo grueso = vía única (Chepe). "
                   "Cuadros = cocheras. Disposición inicial y de fin de día del gráfico de rotaciones.")
    else:
        st.caption("L1 en carril simple (ida arriba / vuelta abajo). Rojo = vía única "
                   "(Hualqui–La Leonera, Mercado–El Arenal). Cuadros = cocheras.")
    g = GEO[linea]
    grid = _load("estado_grilla.csv", _mt("estado_grilla.csv"))
    cocheras = _load("cocheras.csv", _mt("cocheras.csv"))
    cocheras = cocheras[cocheras.linea == linea] if not cocheras.empty else cocheras
    tramos = _tramos(linea)
    enlaces = _load("enlaces.csv", _mt("enlaces.csv"))
    enlaces = enlaces[(enlaces.linea == linea) & (enlaces.km <= g["xmax"])] if not enlaces.empty else pd.DataFrame({"km": []})
    bl = _load("bloques.csv", _mt("bloques.csv"))
    bl = bl[bl.linea == linea] if not bl.empty else pd.DataFrame(columns=["dist_lo", "dist_hi"])
    est_ref = _ref(linea)
    if grid.empty or cocheras.empty:
        st.info("Faltan datos. Corre run_all.py.")
        return
    grid = grid[grid.tramo == linea]

    tiempos = sorted(grid.t_s.unique())
    base = _base(linea, est_ref, cocheras, tramos, enlaces, g)
    nb = len(base)
    fig = go.Figure(data=base + _dyn(grid[grid.t_s == tiempos[0]], linea, tramos, bl, cocheras, g))
    fig.frames = [go.Frame(data=_dyn(grid[grid.t_s == ts], linea, tramos, bl, cocheras, g),
                           traces=[nb, nb + 1, nb + 2], name=_hhmmss(ts)[:5]) for ts in tiempos]
    pasos = [dict(method="animate", label=_hhmmss(ts)[:5],
                  args=[[_hhmmss(ts)[:5]], dict(mode="immediate", frame=dict(duration=0, redraw=True),
                        transition=dict(duration=0))]) for ts in tiempos]
    fig.update_layout(
        height=560, margin=dict(l=10, r=10, t=46, b=10),
        yaxis=dict(visible=False, range=[0.0, 1.06]),
        xaxis=dict(title="km", range=[-0.5, g["xmax"]], showgrid=True, gridcolor="#f4f4f4"),
        updatemenus=[dict(type="buttons", showactive=False, x=0.0, y=1.12, xanchor="left", buttons=[
            dict(label="▶ Reproducir", method="animate",
                 args=[None, dict(frame=dict(duration=140, redraw=True), fromcurrent=True, transition=dict(duration=0))]),
            dict(label="⏸ Pausa", method="animate",
                 args=[[None], dict(mode="immediate", frame=dict(duration=0, redraw=False))])])],
        sliders=[dict(active=0, x=0.06, len=0.92, currentvalue=dict(prefix="Hora: "), steps=pasos)],
        showlegend=False)
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
                 "sentido": x["sentido"], "dist_km": x["dist_km"], "cochera": ""} for x in estd["trenes"] if x["tramo"] == linea]
        rows += [{"estado": "cochera", "unidad": e["unidad"], "servicio": "", "tramo": e["linea"], "sentido": "",
                  "dist_km": e["dist_km"], "cochera": e["cochera"]} for e in estd["estacionados"] if e["linea"] == linea]
        df_t = pd.DataFrame(rows)
        fig2 = go.Figure(data=_base(linea, est_ref, cocheras, tramos, enlaces, g) + _dyn(df_t, linea, tramos, bl, cocheras, g))
        fig2.update_layout(height=420, margin=dict(l=10, r=10, t=30, b=10), title=f"{linea} a las {hh:02d}:{mm:02d}:{ss:02d}",
                           yaxis=dict(visible=False, range=[0.0, 1.06]),
                           xaxis=dict(title="km", range=[-0.5, g["xmax"]]), showlegend=False)
        st.plotly_chart(fig2, use_container_width=True)
        filas = []
        for x in estd["trenes"]:
            if x["tramo"] != linea:
                continue
            via = ""
            if linea == "L2":
                y = _y_via(x["dist_km"], x["sentido"], tramos, g)
                via = "poniente" if y == g["pon"] else ("oriente" if y == g["ori"] else "única")
                ct = _canton(x["dist_km"], bl)
                via += f" · cantón {ct[0]:.1f}–{ct[1]:.1f} km" if ct else ""
            filas.append({"unidad": x["unidad"], "servicio": x["servicio"], "sentido": x["sentido"],
                          "km": x["dist_km"], "vía / cantón": via})
        st.markdown(f"**Trenes circulando en {linea} — vía y cantón**")
        st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)
    except Exception as e:
        st.warning(f"No se pudo calcular el instante exacto: {e}")
