"""App Streamlit — Biotren / Corto Laja.

Datos limpios, optimizacion, Marey (itinerario actual vs optimizado), red de
infraestructura y mapa georreferenciado. Autonoma: lee datos/clean/.
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
st.caption("Datos limpios, optimización, diagrama de Marey, red de infraestructura y mapa.")


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


def marey(linea, archivo, titulo):
    malla = load(archivo)
    requeridas = {"linea", "tren_id", "sentido", "estacion", "dist_km", "hora_min"}
    if malla.empty or not requeridas.issubset(malla.columns):
        st.warning(f"Falta o formato antiguo en {archivo}. Regenera y vuelve a subir.")
        return
    m = malla[malla.linea == linea]
    if m.empty:
        st.info(f"Sin datos para {linea} en {archivo}.")
        return
    sentidos = list(m["sentido"].unique())
    cols = {sentidos[0]: "#1F3864"}
    if len(sentidos) > 1:
        cols[sentidos[1]] = "#C00000"
    fig = go.Figure()
    for tid, g in m.groupby("tren_id"):
        sent = g["sentido"].iloc[0]
        fig.add_trace(go.Scatter(x=g["hora_min"], y=g["dist_km"], mode="lines",
                                 line=dict(color=cols.get(sent, "#808080"), width=1.0),
                                 showlegend=False, hovertext=g["estacion"], hoverinfo="text+x"))
    ek = m[["estacion", "dist_km"]].drop_duplicates().sort_values("dist_km")
    fig.update_yaxes(tickvals=ek["dist_km"], ticktext=ek["estacion"], autorange="reversed")
    ticks = list(range(0, 1441, 120))
    fig.update_xaxes(range=[0, 1440], tickvals=ticks, ticktext=[f"{t//60:02d}:00" for t in ticks])
    for sent in sentidos:
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="lines",
                                 line=dict(color=cols.get(sent), width=2), name=sent))
    fig.update_layout(height=680, title=titulo, xaxis_title="Hora del día", yaxis_title="",
                      margin=dict(l=10, r=10, t=50, b=10),
                      legend=dict(orientation="h", y=1.04, x=0))
    st.plotly_chart(fig, use_container_width=True)


def tab_marey(linea, top, bottom):
    fuente = st.radio("Malla a mostrar", ["Itinerario actual", "Optimizada"],
                      horizontal=True, key=f"src_{linea}")
    archivo = "malla_real.csv" if fuente == "Itinerario actual" else "malla_marey.csv"
    st.caption(f"Día completo. Eje vertical: distancia ({top} arriba, {bottom} abajo). "
               "Cada línea es un tren; el cruce de colores opuestos = un cruzamiento.")
    marey(linea, archivo, f"{linea} — {fuente.lower()}")


tabs = st.tabs([
    "Resumen", "Optimización", "Marey L2", "Marey L1", "Red infraestructura", "Mapa",
    "Material rodante", "Demanda OD", "Perfil de carga", "Itinerario", "Trenes de carga",
])

with tabs[0]:
    st.subheader("Estado de los insumos")
    archivos = {
        "Infraestructura (arcos)": "infra_edges.csv", "Material rodante": "material_rodante.csv",
        "OD por franja": "od_franjas.csv", "Perfil de carga": "perfil_carga.csv",
        "Tiempos itinerario": "itinerario_tiempos.csv", "Salidas reales": "salidas_reales.csv",
        "Malla itinerario actual": "malla_real.csv", "Malla optimizada": "malla_marey.csv",
        "Estaciones geo": "estaciones_geo.csv", "Red (arcos)": "red_arcos.csv",
    }
    filas = [{"Dataset": k, "Filas": len(load(v)), "Archivo": v} for k, v in archivos.items()]
    st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)
    perfil = load("perfil_carga.csv")
    if not perfil.empty:
        st.metric("Servicios sobre capacidad (780 pax)", int(perfil["supera_capacidad"].sum()))

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
            st.markdown("**Sensibilidad al factor de hora punta:**")
            sdf = pd.DataFrame(sens)
            st.plotly_chart(px.line(sdf, x="peak_share", y="flota_pico", markers=True,
                                    labels={"peak_share": "Factor hora punta", "flota_pico": "Flota pico"}),
                            use_container_width=True)
            st.dataframe(sdf, use_container_width=True, hide_index=True)
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
    st.caption("Cada banda es un corredor; las líneas paralelas indican doble vía y los "
               "ensanchamientos, desvíos/cruzamientos. Esquema de OpenTrack.")
    arcos = load("red_arcos.csv"); est = load("red_estaciones.csv")
    if arcos.empty:
        st.info("Falta red_arcos.csv (corre parsers/parse_red_topologia.py).")
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
                                     hovertext=est["label"], hoverinfo="text", showlegend=False))
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
                                           line=dict(width=3, color=colores.get(linea, "#808080")),
                                           marker=dict(size=9, color=colores.get(linea, "#808080")),
                                           name=linea, text=g["estacion"], hoverinfo="text+name"))
        fig.update_layout(mapbox_style="open-street-map",
                          mapbox=dict(center=dict(lat=geo["lat"].mean(), lon=geo["lon"].mean()), zoom=10.2),
                          height=680, margin=dict(l=0, r=0, t=0, b=0),
                          legend=dict(orientation="h", y=0.01, x=0.01))
        st.plotly_chart(fig, use_container_width=True)
        st.caption("L1 (azul): Mercado–Concepción–Hualqui. L2 (rojo): Concepción–Coronel. "
                   "Corto Laja (Hualqui–Laja) pendiente de coordenadas.")

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
        st.dataframe(od, use_container_width=True, hide_index=True)

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
    st.info("Extracción aproximada por coordenadas; validar contra el PDF.")
    st.dataframe(load("carga_caminos.csv"), use_container_width=True, hide_index=True)
