"""Vista 'Simulación en vivo': posición de trenes y ocupación de cocheras.

Animación (play + deslizador) sobre el día completo, y un instante exacto
(HH:MM:SS) con el estado preciso. Lun-Vie, situación actual.
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
AZUL, ROJO, VERDE = "#1F3864", "#C00000", "#2E7D32"


def _hhmmss(s):
    s = int(s)
    return f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}"


@st.cache_data
def _grid(_mt):
    f = CLEAN / "estado_grilla.csv"
    return pd.read_csv(f) if f.exists() else pd.DataFrame()


@st.cache_data
def _ref(_mt):
    f = CLEAN / "malla_real.csv"
    r = pd.read_csv(f) if f.exists() else pd.DataFrame()
    out = {}
    for ln in ["L2", "L1"]:
        if not r.empty:
            out[ln] = (r[r.linea == ln][["estacion", "dist_km"]]
                       .drop_duplicates().sort_values("dist_km").reset_index(drop=True))
        else:
            out[ln] = pd.DataFrame(columns=["estacion", "dist_km"])
    return out


def _ida(sentido):
    return ("->CW" in sentido) or ("->LJ" in sentido)


def _km_de(est_ref, est):
    for ln in ["L2", "L1"]:
        er = est_ref[ln]
        if est in set(er.estacion):
            return ln, float(er[er.estacion == est].dist_km.iloc[0])
    return None, None


def _trenes_cocheras(df_t, est_ref):
    tr = df_t[df_t.estado == "circulando"]
    xs, ys, txt, col = [], [], [], []
    for r in tr.itertuples():
        lane = LANE.get(r.tramo, 0.0)
        xs.append(r.dist_km)
        ys.append(lane + (0.12 if _ida(r.sentido) else -0.12))
        txt.append(f"{r.unidad} · serv {r.servicio} · {r.sentido} · km {r.dist_km}")
        col.append(AZUL if _ida(r.sentido) else ROJO)
    trenes = go.Scatter(x=xs, y=ys, mode="markers", name="trenes",
                        marker=dict(size=12, color=col, line=dict(width=1, color="white")),
                        hovertext=txt, hoverinfo="text")
    coch = df_t[df_t.estado.astype(str).str.startswith("cochera:")]
    cd = {}
    for r in coch.itertuples():
        cd.setdefault(r.estado.split(":", 1)[1], []).append(r.unidad)
    cx, cy, csz, ctx = [], [], [], []
    for est, us in cd.items():
        ln, x = _km_de(est_ref, est)
        if ln is None:
            continue
        cx.append(x); cy.append(LANE[ln] - 0.34)
        csz.append(14 + 5 * len(us)); ctx.append(f"Cochera {est}: {len(us)} automotor(es) → {', '.join(sorted(us))}")
    dep = go.Scatter(x=cx, y=cy, mode="markers+text", name="cocheras",
                     marker=dict(size=csz, color=VERDE, opacity=0.45, symbol="square"),
                     text=[t.split(":")[1].split(" ")[1] for t in ctx] if ctx else None,
                     textposition="middle center", textfont=dict(size=9, color="white"),
                     hovertext=ctx, hoverinfo="text")
    return trenes, dep


def _base(est_ref):
    base = []
    for ln, lane in LANE.items():
        er = est_ref[ln]
        if er.empty:
            continue
        base.append(go.Scatter(x=[er.dist_km.min(), er.dist_km.max()], y=[lane, lane],
                               mode="lines", line=dict(color="#d8d8d8", width=3),
                               hoverinfo="skip", showlegend=False))
        base.append(go.Scatter(x=er.dist_km, y=[lane] * len(er), mode="markers",
                               marker=dict(symbol="line-ns-open", size=12, color="#aaa"),
                               hovertext=er.estacion, hoverinfo="text", showlegend=False))
    return base


def render():
    st.subheader("Simulación en vivo — posición de trenes y cocheras (Lun-Vie)")
    st.caption("Reconstruido de la rotación de los 16 automotores. Posición interpolada entre "
               "estaciones (velocidad constante por tramo). L2 arriba, L1 abajo; azul = sentido "
               "Concepción→Coronel / Mercado→Laja, rojo = inverso; cuadros verdes = cocheras.")
    mt = (CLEAN / "estado_grilla.csv").stat().st_mtime if (CLEAN / "estado_grilla.csv").exists() else 0
    grid = _grid(mt)
    est_ref = _ref(mt)
    if grid.empty:
        st.info("Falta estado_grilla.csv. Corre simulador/estado_dia.py (o run_all.py).")
        return

    tiempos = sorted(grid.t_s.unique())
    base = _base(est_ref)
    n_base = len(base)
    f0 = _trenes_cocheras(grid[grid.t_s == tiempos[0]], est_ref)
    frames = []
    for ts in tiempos:
        tr, dep = _trenes_cocheras(grid[grid.t_s == ts], est_ref)
        frames.append(go.Frame(data=[tr, dep], traces=[n_base, n_base + 1], name=_hhmmss(ts)[:5]))
    fig = go.Figure(data=base + list(f0), frames=frames)
    pasos = [dict(method="animate", label=_hhmmss(ts)[:5],
                  args=[[_hhmmss(ts)[:5]], dict(mode="immediate",
                        frame=dict(duration=0, redraw=True), transition=dict(duration=0))])
             for ts in tiempos]
    fig.update_layout(
        height=540, margin=dict(l=10, r=10, t=30, b=10),
        yaxis=dict(tickvals=[1, 0], ticktext=["L2", "L1"], range=[-0.6, 1.4]),
        xaxis=dict(title="km", showgrid=True, gridcolor="#f3f3f3"),
        updatemenus=[dict(type="buttons", showactive=False, x=0.0, y=1.18, xanchor="left",
                          buttons=[
                              dict(label="▶ Reproducir", method="animate",
                                   args=[None, dict(frame=dict(duration=120, redraw=True),
                                                    fromcurrent=True, transition=dict(duration=0))]),
                              dict(label="⏸ Pausa", method="animate",
                                   args=[[None], dict(mode="immediate", frame=dict(duration=0, redraw=False))])])],
        sliders=[dict(active=0, x=0.08, len=0.9, currentvalue=dict(prefix="Hora: "), steps=pasos)])
    st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.markdown("**Instante exacto** — ingresa una hora y mira el estado en ese segundo:")
    c1, c2, c3 = st.columns([1, 1, 3])
    hh = c1.number_input("Hora", 0, 23, 7)
    mm = c2.number_input("Minuto", 0, 59, 30)
    ss = c3.number_input("Segundo", 0, 59, 0)
    try:
        import estado_dia
        unidades, _ = estado_dia.cargar()
        t = hh * 60 + mm + ss / 60.0
        estd = estado_dia.estado(t, unidades)
        fig2 = go.Figure(data=_base(est_ref) + list(_trenes_cocheras(
            pd.DataFrame([{"estado": "circulando", "unidad": x["unidad"], "servicio": x["servicio"],
                           "tramo": x["tramo"], "sentido": x["sentido"], "dist_km": x["dist_km"]}
                          for x in estd["trenes"]] +
                         [{"estado": f"cochera:{e}", "unidad": u, "servicio": "", "tramo": "",
                           "sentido": "", "dist_km": None}
                          for e, us in estd["cocheras"].items() for u in us]), est_ref)))
        fig2.update_layout(height=360, margin=dict(l=10, r=10, t=10, b=10),
                           yaxis=dict(tickvals=[1, 0], ticktext=["L2", "L1"], range=[-0.6, 1.4]),
                           xaxis=dict(title="km"), showlegend=False)
        st.plotly_chart(fig2, use_container_width=True)
        a, b = st.columns(2)
        a.metric("Trenes circulando", len(estd["trenes"]))
        b.metric("Automotores en cochera", sum(len(v) for v in estd["cocheras"].values()))
        a.markdown("**Trenes en circulación**")
        a.dataframe(pd.DataFrame(estd["trenes"]), use_container_width=True, hide_index=True)
        b.markdown("**Cocheras ocupadas**")
        b.dataframe(pd.DataFrame([{"cochera": e, "n": len(us), "automotores": ", ".join(sorted(us))}
                                  for e, us in sorted(estd["cocheras"].items())]),
                    use_container_width=True, hide_index=True)
    except Exception as e:
        st.warning(f"No se pudo calcular el instante exacto: {e}")
