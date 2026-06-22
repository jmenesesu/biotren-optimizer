"""App Streamlit — Biotren / Corto Laja.

Explora los datos limpios, los resultados del optimizador y dos vistas graficas:
el diagrama de Marey (tiempo-distancia de la malla) y el mapa georreferenciado.

La app es autonoma: lee solo de datos/clean/ (versionado), por lo que funciona en
Streamlit Community Cloud sin los insumos crudos.

Uso local:
    streamlit run app/streamlit_app.py
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
st.caption("Datos limpios, optimización de capacidad y vistas gráficas (malla y mapa).")


@st.cache_data
def load(nombre):
    f = CLEAN / nombre
    return pd.read_csv(f) if f.exists() else pd.DataFrame()


def load_json(nombre):
    f = CLEAN / nombre
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


tabs = st.tabs([
    "Resumen", "Optimización", "Diagrama de Marey", "Mapa",
    "Infraestructura", "Material rodante", "Demanda OD", "Perfil de carga",
    "Itinerario", "Trenes de carga",
])

# ---------------- Resumen ----------------
with tabs[0]:
    st.subheader("Estado de los insumos")
    archivos = {
        "Arcos de infraestructura": "infra_edges.csv",
        "Material rodante": "material_rodante.csv",
        "OD por franja": "od_franjas.csv",
        "Perfil de carga": "perfil_carga.csv",
        "Tiempos de itinerario": "itinerario_tiempos.csv",
        "Caminos de carga": "carga_caminos.csv",
        "Malla (Marey)": "malla_marey.csv",
    }
    filas = [{"Dataset": k, "Filas": len(load(v)), "Archivo": v} for k, v in archivos.items()]
    st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)
    perfil = load("perfil_carga.csv")
    if not perfil.empty:
        st.metric("Servicios sobre capacidad (780 pax)", int(perfil["supera_capacidad"].sum()))

# ---------------- Optimización ----------------
with tabs[1]:
    st.subheader("Optimización de capacidad y flota — hora punta")
    res = load_json("optim_resumen.json")
    fr = load("optim_frecuencias.csv")
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
                                    labels={"peak_share": "Factor de hora punta",
                                            "flota_pico": "Flota pico necesaria"}),
                            use_container_width=True)
            st.dataframe(sdf, use_container_width=True, hide_index=True)
    if not fr.empty:
        st.dataframe(fr, use_container_width=True, hide_index=True)

# ---------------- Diagrama de Marey ----------------
with tabs[2]:
    st.subheader("Diagrama de Marey — malla L2 (Concepción ↔ Coronel)")
    st.caption("Cada línea diagonal es un tren. Eje X: tiempo (min). Eje Y: distancia (km). "
               "El cruce de líneas de sentidos opuestos indica un cruzamiento.")
    malla = load("malla_marey.csv")
    if malla.empty:
        st.info("Falta malla_marey.csv. Genera con: python optimizador/generar_malla.py")
    else:
        fig = go.Figure()
        colores = {"CC->CW": "#1F3864", "CW->CC": "#C00000"}
        for tid, g in malla.groupby("tren_id"):
            sent = g["sentido"].iloc[0]
            fig.add_trace(go.Scatter(
                x=g["t_min"], y=g["km"], mode="lines",
                line=dict(color=colores.get(sent, "#808080"), width=1.2),
                name=sent, legendgroup=sent, showlegend=False,
                hovertext=g["estacion"], hoverinfo="text+x+y"))
        # marcar estaciones en el eje Y
        est_km = (malla[["estacion", "km"]].drop_duplicates().sort_values("km"))
        fig.update_yaxes(tickvals=est_km["km"], ticktext=est_km["estacion"])
        fig.update_layout(height=650, xaxis_title="Tiempo (min)", yaxis_title="",
                          margin=dict(l=10, r=10, t=30, b=10))
        # leyenda manual
        for sent, col in colores.items():
            fig.add_trace(go.Scatter(x=[None], y=[None], mode="lines",
                                     line=dict(color=col, width=2), name=sent))
        st.plotly_chart(fig, use_container_width=True)

# ---------------- Mapa ----------------
with tabs[3]:
    st.subheader("Mapa georreferenciado de la red")
    geo = load("estaciones_geo.csv")
    if geo.empty or not {"lat", "lon", "linea"}.issubset(geo.columns):
        st.info("Falta estaciones_geo.csv con columnas: estacion, linea, orden, lat, lon.")
    else:
        if "fuente" in geo.columns and geo["fuente"].astype(str).str.contains("aproximada").any():
            st.warning("Hay coordenadas aproximadas. Reemplaza por tu archivo GIS real.")
        colores = {"L1": "#1F3864", "L2": "#C00000"}
        fig = go.Figure()
        for linea, g in geo.sort_values(["linea", "orden"]).groupby("linea"):
            fig.add_trace(go.Scattermapbox(
                lat=g["lat"], lon=g["lon"], mode="lines+markers",
                line=dict(width=3, color=colores.get(linea, "#808080")),
                marker=dict(size=9, color=colores.get(linea, "#808080")),
                name=linea, text=g["estacion"], hoverinfo="text+name"))
        fig.update_layout(
            mapbox_style="open-street-map",
            mapbox=dict(center=dict(lat=geo["lat"].mean(), lon=geo["lon"].mean()), zoom=10.2),
            height=680, margin=dict(l=0, r=0, t=0, b=0),
            legend=dict(orientation="h", yanchor="bottom", y=0.01, xanchor="left", x=0.01))
        st.plotly_chart(fig, use_container_width=True)
        st.caption("L1 (azul): Mercado–Concepción–Hualqui. L2 (rojo): Concepción–Coronel.")
        with st.expander("Ver coordenadas"):
            st.dataframe(geo, use_container_width=True, hide_index=True)

# ---------------- Infraestructura ----------------
with tabs[4]:
    st.subheader("Infraestructura por corredor")
    st.dataframe(load("infra_resumen_corredores.csv"), use_container_width=True, hide_index=True)
    with st.expander("Ver arcos (detalle)"):
        st.dataframe(load("infra_edges.csv"), use_container_width=True, hide_index=True)

# ---------------- Material rodante ----------------
with tabs[5]:
    st.subheader("Flota Biotren")
    mr = load("material_rodante.csv")
    if not mr.empty:
        st.dataframe(mr[mr["flota_biotren"]], use_container_width=True, hide_index=True)

# ---------------- Demanda OD ----------------
with tabs[6]:
    st.subheader("Demanda OD por franja")
    od = load("od_franjas.csv")
    if not od.empty:
        st.bar_chart(od.groupby("franja")["viajes"].sum())
        st.dataframe(od, use_container_width=True, hide_index=True)

# ---------------- Perfil de carga ----------------
with tabs[7]:
    st.subheader("Perfil de carga por servicio")
    perfil = load("perfil_carga.csv")
    if not perfil.empty:
        st.dataframe(perfil.sort_values("afluencia", ascending=False),
                     use_container_width=True, hide_index=True)

# ---------------- Itinerario ----------------
with tabs[8]:
    st.subheader("Tiempos del itinerario (referencia del motor)")
    st.dataframe(load("itinerario_tiempos.csv"), use_container_width=True, hide_index=True)

# ---------------- Trenes de carga ----------------
with tabs[9]:
    st.subheader("Caminos de trenes de carga (restricción fija)")
    st.info("Extracción aproximada por coordenadas; validar contra el PDF.")
    st.dataframe(load("carga_caminos.csv"), use_container_width=True, hide_index=True)
