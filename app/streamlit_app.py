"""App Streamlit — Biotren / Corto Laja.

Datos limpios, optimizacion de capacidad y vistas graficas: diagrama de Marey
(por linea, dia completo) y mapa georreferenciado. Autonoma: lee datos/clean/.

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


def marey(linea, titulo, origen_arriba=True):
    """Dibuja el diagrama de Marey de una linea (dia completo, ambos sentidos)."""
    malla = load("malla_marey.csv")
    if malla.empty or "linea" not in malla.columns:
        st.info("Falta malla_marey.csv. Genera con: python optimizador/generar_malla.py")
        return
    m = malla[malla.linea == linea]
    if m.empty:
        st.info(f"Sin malla para {linea}.")
        return
    sentidos = list(m["sentido"].unique())
    cols = {sentidos[0]: "#1F3864", sentidos[1] if len(sentidos) > 1 else "x": "#C00000"}
    fig = go.Figure()
    for tid, g in m.groupby("tren_id"):
        sent = g["sentido"].iloc[0]
        fig.add_trace(go.Scatter(
            x=g["hora_min"], y=g["dist_km"], mode="lines",
            line=dict(color=cols.get(sent, "#808080"), width=1.0),
            showlegend=False, hovertext=g["estacion"], hoverinfo="text+x"))
    # estaciones en el eje Y
    ek = m[["estacion", "dist_km"]].drop_duplicates().sort_values("dist_km")
    fig.update_yaxes(tickvals=ek["dist_km"], ticktext=ek["estacion"],
                     autorange="reversed" if origen_arriba else True)
    # eje X: dia completo con marcas cada 2 h
    ticks = list(range(0, 1441, 120))
    fig.update_xaxes(range=[0, 1440], tickvals=ticks,
                     ticktext=[f"{t//60:02d}:00" for t in ticks])
    # leyenda manual de sentidos
    for sent in sentidos:
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="lines",
                                 line=dict(color=cols.get(sent), width=2), name=sent))
    fig.update_layout(height=680, title=titulo, xaxis_title="Hora del día",
                      yaxis_title="", margin=dict(l=10, r=10, t=50, b=10),
                      legend=dict(orientation="h", y=1.04, x=0))
    st.plotly_chart(fig, use_container_width=True)


tabs = st.tabs([
    "Resumen", "Optimización", "Marey L2", "Marey L1", "Mapa",
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
        "Estaciones geo": "estaciones_geo.csv",
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

# ---------------- Marey L2 ----------------
with tabs[2]:
    st.subheader("Diagrama de Marey — Línea 2 (Concepción ↔ Coronel)")
    st.caption("Día completo. Eje vertical: distancia (Concepción arriba, Coronel abajo). "
               "Cada línea es un tren; el cruce de colores opuestos = un cruzamiento.")
    marey("L2", "L2 — malla del día", origen_arriba=True)

# ---------------- Marey L1 ----------------
with tabs[3]:
    st.subheader("Diagrama de Marey — Línea 1 (Mercado ↔ Hualqui ↔ Laja)")
    st.caption("Día completo. Eje vertical: distancia (Mercado arriba, Laja abajo, "
               "Concepción intermedia). Cada línea es un tren.")
    marey("L1", "L1 — malla del día", origen_arriba=True)

# ---------------- Mapa ----------------
with tabs[4]:
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
        st.caption("L1 (azul): Mercado–Concepción–Hualqui. L2 (rojo): Concepción–Coronel. "
                   "Corto Laja (Hualqui–Laja) pendiente de coordenadas.")

# ---------------- Infraestructura ----------------
with tabs[5]:
    st.subheader("Infraestructura por corredor")
    st.dataframe(load("infra_resumen_corredores.csv"), use_container_width=True, hide_index=True)
    with st.expander("Ver arcos (detalle)"):
        st.dataframe(load("infra_edges.csv"), use_container_width=True, hide_index=True)

# ---------------- Material rodante ----------------
with tabs[6]:
    st.subheader("Flota Biotren")
    mr = load("material_rodante.csv")
    if not mr.empty:
        st.dataframe(mr[mr["flota_biotren"]], use_container_width=True, hide_index=True)

# ---------------- Demanda OD ----------------
with tabs[7]:
    st.subheader("Demanda OD por franja")
    od = load("od_franjas.csv")
    if not od.empty:
        st.bar_chart(od.groupby("franja")["viajes"].sum())
        st.dataframe(od, use_container_width=True, hide_index=True)

# ---------------- Perfil de carga ----------------
with tabs[8]:
    st.subheader("Perfil de carga por servicio")
    perfil = load("perfil_carga.csv")
    if not perfil.empty:
        st.dataframe(perfil.sort_values("afluencia", ascending=False),
                     use_container_width=True, hide_index=True)

# ---------------- Itinerario ----------------
with tabs[9]:
    st.subheader("Tiempos del itinerario (referencia del motor)")
    st.dataframe(load("itinerario_tiempos.csv"), use_container_width=True, hide_index=True)

# ---------------- Trenes de carga ----------------
with tabs[10]:
    st.subheader("Caminos de trenes de carga (restricción fija)")
    st.info("Extracción aproximada por coordenadas; validar contra el PDF.")
    st.dataframe(load("carga_caminos.csv"), use_container_width=True, hide_index=True)
