"""App Streamlit — Biotren / Corto Laja.

Marey (itinerario actual vs optimizado) con color por automotor, tramos de via
unica y deteccion de cruzamientos; red de infraestructura; mapa; datos.
Autonoma: lee datos/clean/.
"""
import json
import sys
from pathlib import Path
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO / "parsers"))
CLEAN = REPO / "datos" / "clean"

st.set_page_config(page_title="Biotren — Optimizador de itinerarios", layout="wide")
st.title("Biotren / Corto Laja — Modelo de optimización de itinerarios")
st.caption("Marey con color por automotor y vía única, red de infraestructura, mapa y datos.")

PALETA = (px.colors.qualitative.Dark24 + px.colors.qualitative.Light24)


@st.cache_data
def _load_cached(nombre, _mtime):
    f = CLEAN / nombre
    return pd.read_csv(f) if f.exists() else pd.DataFrame()


def load(nombre):
    f = CLEAN / nombre
    mt = f.stat().st_mtime if f.exists() else 0.0
    return _load_cached(nombre, mt)


def load_json(nombre):
    f = CLEAN / nombre
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def marey(linea, archivo, titulo, mostrar_via_unica=True, mostrar_conflictos=True):
    malla = load(archivo)
    req = {"linea", "tren_id", "dist_km", "hora_min"}
    if malla.empty or not req.issubset(malla.columns):
        st.warning(f"Falta o formato antiguo en {archivo}.")
        return
    m = malla[malla.linea == linea].copy()
    if m.empty:
        st.info(f"Sin datos para {linea}.")
        return
    tiene_unidad = "unidad" in m.columns and m["unidad"].astype(str).str.len().gt(0).any()
    fig = go.Figure()

    # bandas de via unica (rectangulos horizontales en todo el ancho de tiempo)
    vu = load("via_unica.csv")
    if mostrar_via_unica and not vu.empty:
        for _, r in vu[vu.linea == linea].iterrows():
            fig.add_hrect(y0=r.dist_lo, y1=r.dist_hi,
                          fillcolor="rgba(192,0,0,0.07)" if r.bloquea else "rgba(128,128,128,0.06)",
                          line_width=0, layer="below",
                          annotation_text=f"vía única: {r.nombre}", annotation_position="top left",
                          annotation_font_size=9)

    # trenes
    if tiene_unidad:
        unidades = sorted(m["unidad"].dropna().unique())
        cmap = {u: PALETA[i % len(PALETA)] for i, u in enumerate(unidades)}
        vistos = set()
        for tid, g in m.groupby("tren_id"):
            u = g["unidad"].iloc[0]
            fig.add_trace(go.Scatter(
                x=g["hora_min"], y=g["dist_km"], mode="lines",
                line=dict(color=cmap.get(u, "#888"), width=1.4),
                name=u, legendgroup=u, showlegend=(u not in vistos),
                hovertext=[f"{u} · {e}" for e in (g["estacion"] if "estacion" in g else g["dist_km"])], hoverinfo="text+x"))
            vistos.add(u)
    else:
        cols = {"CC->CW": "#1F3864", "CW->CC": "#C00000",
                "TH->LJ": "#1F3864", "LJ->TH": "#C00000"}
        for tid, g in m.groupby("tren_id"):
            sent = g["sentido"].iloc[0]
            fig.add_trace(go.Scatter(x=g["hora_min"], y=g["dist_km"], mode="lines",
                                     line=dict(color=cols.get(sent, "#888"), width=1.1),
                                     showlegend=False, hovertext=(g["estacion"] if "estacion" in g else g["dist_km"]), hoverinfo="text+x"))

    # conflictos (solo malla real)
    cf = load("conflictos.csv")
    if mostrar_conflictos and not cf.empty and "linea" in cf.columns:
        c = cf[cf.linea == linea]
        if not c.empty:
            fig.add_trace(go.Scatter(
                x=c["hora_mid"], y=c["dist_mid"], mode="markers",
                marker=dict(symbol="x", size=10, color="#C00000", line=dict(width=1)),
                name="cruce en vía única", legendgroup="conf",
                hovertext=[f"{a} × {b}" for a, b in zip(c["tren_a"], c["tren_b"])],
                hoverinfo="text"))

    if "estacion" in m.columns and m["estacion"].notna().any():
        ek = m[["estacion", "dist_km"]].dropna().drop_duplicates().sort_values("dist_km")
    else:
        ref = load("malla_real.csv")
        ek = (ref[ref.linea == linea][["estacion", "dist_km"]].drop_duplicates().sort_values("dist_km")
              if not ref.empty else pd.DataFrame(columns=["estacion", "dist_km"]))
    if not ek.empty:
        fig.update_yaxes(tickvals=ek["dist_km"], ticktext=ek["estacion"], autorange="reversed",
                         showgrid=True, gridcolor="#eee")
    else:
        fig.update_yaxes(autorange="reversed", showgrid=True, gridcolor="#eee")
    ticks = list(range(0, 1441, 60))
    fig.update_xaxes(range=[0, 1440], tickvals=ticks,
                     ticktext=[f"{t//60:02d}" for t in ticks], showgrid=True, gridcolor="#f3f3f3")
    fig.update_layout(height=720, title=titulo, xaxis_title="Hora del día", yaxis_title="",
                      margin=dict(l=10, r=10, t=50, b=10), hovermode="closest",
                      legend=dict(title="Automotor", font=dict(size=9)))
    st.plotly_chart(fig, use_container_width=True)


ARCH_MALLA = {"Itinerario actual": "malla_real.csv",
              "Simulada (fixed-block)": "malla_sim.csv",
              "Optimizada": "malla_marey.csv"}


def tab_marey(linea, top, bottom):
    fuente = st.radio("Malla", list(ARCH_MALLA), horizontal=True, key=f"src_{linea}")
    archivo = ARCH_MALLA[fuente]
    st.caption(f"Día completo. Distancia: {top} arriba, {bottom} abajo. Color = automotor. "
               "Banda roja = vía única.")
    marey(linea, archivo, f"{linea} — {fuente.lower()}", mostrar_conflictos=False)
    if fuente == "Simulada (fixed-block)":
        res = load_json("sim_resumen.json")
        if res and res.get("linea") == linea:
            c1, c2, c3 = st.columns(3)
            c1.metric("Trenes simulados", res.get("trenes", 0))
            c2.metric("Esperas en vía única", res.get("esperas_via_unica", 0))
            c3.metric("Espera total (min)", res.get("espera_total_min", 0))
            st.caption("Simulación fixed-block: un tren por cantón de vía única; los trenes "
                       "esperan para cruzar. La doble vía se modela con múltiples blocks (libre). "
                       "El tiempo de ocupación del cantón puede afinarse (incluir cambio de cabina).")
        elif linea != "L2":
            st.info("Simulación implementada por ahora solo para L2.")


tabs = st.tabs([
    "Resumen", "Optimización", "Marey L2", "Marey L1", "Red infraestructura", "Mapa",
    "Material rodante", "Demanda OD", "Perfil de carga", "Itinerario", "Trenes de carga",
])

with tabs[0]:
    st.subheader("Estado de los insumos")
    archivos = {
        "Infraestructura (arcos)": "infra_edges.csv", "Material rodante": "material_rodante.csv",
        "OD por franja": "od_franjas.csv", "Perfil de carga": "perfil_carga.csv",
        "Salidas reales": "salidas_reales.csv", "Malla itinerario actual": "malla_real.csv",
        "Malla optimizada": "malla_marey.csv", "Vía única": "via_unica.csv",
        "Conflictos": "conflictos.csv", "Estaciones geo": "estaciones_geo.csv",
    }
    filas = [{"Dataset": k, "Filas": len(load(v)), "Archivo": v} for k, v in archivos.items()]
    st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)

with tabs[1]:
    st.subheader("Optimización de capacidad y flota — hora punta")
    res = load_json("optim_resumen.json"); fr = load("optim_frecuencias.csv")
    if res:
        c1, c2, c3 = st.columns(3)
        c1.metric("Cobertura demanda punta", f"{res['cobertura_pct']}%")
        c2.metric("Flota pico usada", f"{res['flota_pico_usada']} / {res['flota_total']}")
        c3.metric("¿Flota suficiente?", "Sí" if res.get("flota_suficiente") else "No")
        st.caption(res.get("nota", ""))
        sens = res.get("sensibilidad_peak_share")
        if sens:
            sdf = pd.DataFrame(sens)
            st.plotly_chart(px.line(sdf, x="peak_share", y="flota_pico", markers=True,
                                    labels={"peak_share": "Factor hora punta", "flota_pico": "Flota pico"}),
                            use_container_width=True)
    if not fr.empty:
        st.dataframe(fr, use_container_width=True, hide_index=True)

with tabs[2]:
    st.subheader("Diagrama de Marey — Línea 2 (Concepción ↔ Coronel)")
    tab_marey("L2", "Concepción", "Coronel")

with tabs[3]:
    st.subheader("Diagrama de Marey — Línea 1 (Mercado ↔ Hualqui ↔ Laja)")
    tab_marey("L1", "Mercado", "Laja")

with tabs[4]:
    st.subheader("Red de infraestructura (esquema por corredor)")
    st.caption("Cada banda es un corredor; líneas paralelas = doble vía; ensanchamientos = "
               "desvíos/cruzamientos. Esquema de OpenTrack.")
    arcos = load("red_arcos.csv"); est = load("red_estaciones.csv")
    if arcos.empty:
        st.info("Falta red_arcos.csv.")
    else:
        xs, ys = [], []
        for _, r in arcos.iterrows():
            xs += [r.x1, r.x2, None]; ys += [r.y1, r.y2, None]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines",
                                 line=dict(color="#1F3864", width=0.8), hoverinfo="skip", showlegend=False))
        if not est.empty:
            fig.add_trace(go.Scatter(x=est["x"], y=est["y"], mode="markers+text",
                                     marker=dict(color="#C00000", size=7), text=est["label"],
                                     textposition="top center", textfont=dict(size=8),
                                     hoverinfo="text", showlegend=False))
        anns = []
        if "nombre" in arcos.columns:
            for nombre, g in arcos.groupby("nombre"):
                anns.append(dict(x=g[["x1", "x2"]].min().min(), y=g["y1"].median(),
                                 text=nombre, showarrow=False, xanchor="right",
                                 font=dict(color="#C00000", size=11)))
        fig.update_layout(height=820, margin=dict(l=10, r=10, t=10, b=10),
                          yaxis=dict(visible=False), xaxis=dict(visible=False), annotations=anns)
        st.plotly_chart(fig, use_container_width=True)

with tabs[5]:
    st.subheader("Mapa georreferenciado de la red")
    geo = load("estaciones_geo.csv")
    if geo.empty or not {"lat", "lon", "linea"}.issubset(geo.columns):
        st.info("Falta estaciones_geo.csv.")
    else:
        colores = {"L1": "#1F3864", "L2": "#C00000"}
        fig = go.Figure()
        for linea, g in geo.sort_values(["linea", "orden"]).groupby("linea"):
            fig.add_trace(go.Scattermapbox(lat=g["lat"], lon=g["lon"], mode="lines+markers",
                                           line=dict(width=3, color=colores.get(linea, "#888")),
                                           marker=dict(size=9, color=colores.get(linea, "#888")),
                                           name=linea, text=g["estacion"], hoverinfo="text+name"))
        fig.update_layout(mapbox_style="open-street-map",
                          mapbox=dict(center=dict(lat=geo["lat"].mean(), lon=geo["lon"].mean()), zoom=10.2),
                          height=680, margin=dict(l=0, r=0, t=0, b=0),
                          legend=dict(orientation="h", y=0.01, x=0.01))
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Corto Laja (Hualqui–Laja) pendiente de coordenadas.")

with tabs[6]:
    st.subheader("Flota Biotren")
    mr = load("material_rodante.csv")
    if not mr.empty:
        st.dataframe(mr[mr["flota_biotren"]], use_container_width=True, hide_index=True)

with tabs[7]:
    st.subheader("Demanda OD por franja")
    od = load("od_franjas.csv")
    if not od.empty:
        st.bar_chart(od.groupby("franja")["viajes"].sum())

with tabs[8]:
    st.subheader("Perfil de carga por servicio")
    perfil = load("perfil_carga.csv")
    if not perfil.empty:
        st.dataframe(perfil.sort_values("afluencia", ascending=False),
                     use_container_width=True, hide_index=True)

with tabs[9]:
    st.subheader("Tiempos del itinerario (referencia del motor)")
    st.dataframe(load("itinerario_tiempos.csv"), use_container_width=True, hide_index=True)

with tabs[10]:
    st.subheader("Caminos de trenes de carga (restricción fija)")
    st.info("Extracción aproximada; validar contra el PDF.")
    st.dataframe(load("carga_caminos.csv"), use_container_width=True, hide_index=True)
