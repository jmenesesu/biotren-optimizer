"""App Streamlit — Biotren / Corto Laja.

Etapa 1 (situacion actual): horarios limpios (pasajeros + carga), diagramas de
Marey, red de infraestructura y mapa. Etapa 2: optimizacion. Autonoma: datos/clean/.
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

st.set_page_config(page_title="Biotren — Modelo de itinerarios", layout="wide")
st.title("Biotren / Corto Laja — Modelo de optimización de itinerarios")
st.caption("Etapa 1: horarios limpios y diagramas (situación actual). Etapa 2: optimización.")

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


def marey(linea, archivo, titulo, con_carga=False):
    malla = load(archivo)
    req = {"linea", "tren_id", "dist_km", "hora_min"}
    if malla.empty or not req.issubset(malla.columns):
        st.warning(f"Falta o formato antiguo en {archivo}.")
        return
    m = malla[malla.linea == linea].copy()
    if m.empty:
        st.info(f"Sin datos para {linea}.")
        return
    fig = go.Figure()
    # bandas de via unica
    vu = load("via_unica.csv")
    if not vu.empty:
        for _, r in vu[vu.linea == linea].iterrows():
            fig.add_hrect(y0=r.dist_lo, y1=r.dist_hi,
                          fillcolor="rgba(192,0,0,0.06)" if r.bloquea else "rgba(128,128,128,0.05)",
                          line_width=0, layer="below",
                          annotation_text=f"vía única: {r.nombre}", annotation_position="top left",
                          annotation_font_size=9)
    # limites de canton (señales) dentro de la via unica
    blo = load("bloques.csv")
    if not blo.empty:
        bl = blo[(blo.linea == linea) & (blo.tipo == "single")]
        for _, b in bl.iterrows():
            for y in (b.dist_lo, b.dist_hi):
                fig.add_hline(y=y, line_width=0.6, line_dash="dot", line_color="rgba(46,125,50,0.5)")
    # PASAJEROS: color por automotor, linea continua
    tiene_unidad = "unidad" in m.columns and m["unidad"].astype(str).str.len().gt(0).any()
    if tiene_unidad:
        unidades = sorted(m["unidad"].dropna().unique())
        cmap = {u: PALETA[i % len(PALETA)] for i, u in enumerate(unidades)}
        vistos = set()
        for tid, g in m.groupby("tren_id"):
            u = g["unidad"].iloc[0]
            vac = bool(g["equipo_vacio"].iloc[0]) if "equipo_vacio" in g.columns else False
            serv = str(tid).split("-")[-1]
            fig.add_trace(go.Scatter(x=g["hora_min"], y=g["dist_km"], mode="lines",
                                     line=dict(color=cmap.get(u, "#888"), width=1.3,
                                               dash="dot" if vac else "solid"),
                                     name=u, legendgroup=u, showlegend=(u not in vistos),
                                     hovertext=[f"Servicio {serv}{' (vacío)' if vac else ''} · {u} · {e}"
                                                for e in (g["estacion"] if "estacion" in g.columns else g["dist_km"])],
                                     hoverinfo="text+x"))
            vistos.add(u)
    else:
        cols = {"CC->CW": "#1F3864", "CW->CC": "#C00000", "TH->LJ": "#1F3864", "LJ->TH": "#C00000"}
        for tid, g in m.groupby("tren_id"):
            fig.add_trace(go.Scatter(x=g["hora_min"], y=g["dist_km"], mode="lines",
                                     line=dict(color=cols.get(g["sentido"].iloc[0], "#888"), width=1.1),
                                     showlegend=False, hoverinfo="x"))
    # CARGA: gris oscuro, segmentada
    if con_carga:
        mc = load("malla_carga.csv")
        if not mc.empty:
            c = mc[mc.linea == linea]
            primero = True
            for tid, g in c.groupby("tren_id"):
                g = g.sort_values("hora_min")
                tnum = str(tid).replace("C-", "")
                est_c = g["estacion"] if "estacion" in g.columns else [tid]*len(g)
                fig.add_trace(go.Scatter(x=g["hora_min"], y=g["dist_km"], mode="lines",
                                         line=dict(color="#404040", width=1.3, dash="dash"),
                                         name="carga", legendgroup="carga", showlegend=primero,
                                         hovertext=[f"Carga {tnum} · {e}" for e in est_c], hoverinfo="text+x"))
                primero = False
    # eje Y con estaciones
    if "estacion" in m.columns and m["estacion"].notna().any():
        ek = m[["estacion", "dist_km"]].dropna().drop_duplicates().sort_values("dist_km")
    else:
        ref = load("malla_real.csv")
        ek = (ref[ref.linea == linea][["estacion", "dist_km"]].drop_duplicates().sort_values("dist_km")
              if not ref.empty else pd.DataFrame())
    rev = "reversed" if linea == "L2" else True   # L2: Concepción arriba; L1: Mercado arriba
    if not ek.empty:
        fig.update_yaxes(tickvals=ek["dist_km"], ticktext=ek["estacion"], autorange=rev,
                         showgrid=True, gridcolor="#eee")
    else:
        fig.update_yaxes(autorange=rev)
    ticks = list(range(0, 1441, 60))
    fig.update_xaxes(range=[0, 1440], tickvals=ticks, ticktext=[f"{t//60:02d}" for t in ticks],
                     showgrid=True, gridcolor="#f3f3f3")
    fig.update_layout(height=720, title=titulo, xaxis_title="Hora del día", yaxis_title="",
                      margin=dict(l=10, r=10, t=50, b=10), legend=dict(title="", font=dict(size=9)))
    st.plotly_chart(fig, use_container_width=True)


ARCH_MALLA = {"Itinerario actual": "malla_real.csv", "Simulada (fixed-block)": "malla_sim.csv",
              "Reprogramada (sin cruces)": "malla_opt.csv", "Óptima (frecuencias)": "malla_marey.csv"}


def tab_marey(linea, top, bottom):
    fuente = st.radio("Malla", list(ARCH_MALLA), horizontal=True, key=f"src_{linea}")
    st.caption(f"Día completo. Distancia: {top} arriba, {bottom} abajo. Pasajeros: color por "
               "automotor (continua); equipo vacío punteado. Carga: gris segmentado. Banda roja = vía única.")
    marey(linea, ARCH_MALLA[fuente], f"{linea} — {fuente.lower()}", con_carga=True)
    if fuente == "Simulada (fixed-block)":
        res = load_json("sim_resumen.json").get(linea, {})
        if res and res.get("trenes", 0) > 0:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Trenes simulados", res.get("trenes", 0))
            c2.metric("Esperas en vía única", res.get("esperas_via_unica", 0))
            c3.metric("Espera total (min)", res.get("espera_total_min", 0))
            c4.metric("Espera máx (min)", res.get("espera_max_min", 0))
        else:
            st.info(f"Sin simulación disponible para {linea}.")
    if fuente == "Reprogramada (sin cruces)":
        res = load_json("opt_resumen.json").get(linea, {})
        if res:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Cruzamientos antes", res.get("cruzamientos_antes", 0))
            c2.metric("Cruzamientos después", res.get("cruzamientos_despues", 0))
            c3.metric("Trenes reprogramados", res.get("trenes_reprogramados", 0))
            c4.metric("Desfase máx (min)", res.get("desfase_max_min", 0))
            st.caption("Optimizador de timetabling: desplaza salidas (mín. desviación, "
                       f"≤ ±{res.get('delta_permitido', 0)} min) para eliminar cruzamientos en "
                       "vía única. Tiempos de recorrido tomados de horarios_limpios.")


def _hhmm(x):
    import math
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return ""
    h = int(x // 60) % 24; m = int(round(x % 60))
    return f"{h:02d}:{m:02d}" if m < 60 else f"{(h+1)%24:02d}:00"


tabs = st.tabs([
    "Resumen", "Horarios", "Marey L2", "Marey L1", "Red infraestructura", "Mapa",
    "Optimización", "Material rodante", "Demanda OD", "Perfil de carga",
])

# ---------- Resumen ----------
with tabs[0]:
    st.subheader("Estado de los insumos (Etapa 1: situación actual)")
    hl = load("horarios_limpios.csv")
    if not hl.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("Servicios de pasajeros", int(hl[hl.fuente == "pasajeros"]["servicio"].nunique()))
        c2.metric("Trenes de carga", int(hl[hl.fuente == "carga"]["servicio"].nunique()))
        c3.metric("Filas de horario", len(hl))
    archivos = {
        "Horarios limpios (pax+carga)": "horarios_limpios.csv", "Infraestructura": "infra_edges.csv",
        "Material rodante": "material_rodante.csv", "Malla itinerario actual": "malla_real.csv",
        "Malla carga (L1)": "malla_carga.csv", "Vía única": "via_unica.csv",
        "Estaciones geo": "estaciones_geo.csv",
    }
    st.dataframe(pd.DataFrame([{"Dataset": k, "Filas": len(load(v)), "Archivo": v}
                               for k, v in archivos.items()]),
                 use_container_width=True, hide_index=True)

# ---------- Horarios (Etapa 1) ----------
with tabs[1]:
    st.subheader("Horarios limpios — Etapa 1 (extraídos de los itinerarios)")
    hl = load("horarios_limpios.csv")
    if hl.empty:
        st.info("Falta horarios_limpios.csv (corre etl/construir.py).")
    else:
        fuente = st.radio("Tipo", sorted(hl["fuente"].unique()), horizontal=True, key="hf")
        d = hl[hl.fuente == fuente]
        if fuente == "pasajeros":
            c1, c2, c3 = st.columns(3)
            tr = c1.selectbox("Tramo", sorted(d["tramo"].unique()), key="ht")
            se = c2.selectbox("Sentido", sorted(d[d.tramo == tr]["sentido"].unique()), key="hs")
            di = c3.selectbox("Día", sorted(d["tipo_dia"].unique()), key="hd")
            dd = d[(d.tramo == tr) & (d.sentido == se) & (d.tipo_dia == di)].copy()
            dd["hora"] = dd["salida_min"].map(_hhmm)
            est_order = dd.sort_values("orden")["estacion"].drop_duplicates().tolist()
            piv = dd.pivot_table(index="estacion", columns="servicio", values="hora", aggfunc="first")
            piv = piv.reindex(est_order).reset_index()
            st.caption(f"{dd['servicio'].nunique()} servicios · hora de salida por estación. "
                       "Equipos vacíos y automotor: ver tabla de detalle abajo.")
            st.dataframe(piv, use_container_width=True, hide_index=True, height=520)
            with st.expander("Detalle (servicio, automotor, equipo vacío)"):
                det = (dd.groupby("servicio").agg(unidad=("unidad", "first"),
                       equipo_vacio=("equipo_vacio", "first")).reset_index())
                st.dataframe(det, use_container_width=True, hide_index=True)
        else:
            po = st.selectbox("Portador", sorted(d["portador"].unique()), key="hp")
            dd = d[d.portador == po].copy()
            dd["llegada"] = dd["llegada_min"].map(_hhmm); dd["salida"] = dd["salida_min"].map(_hhmm)
            st.caption(f"{dd['servicio'].nunique()} trenes de carga ({po}).")
            st.dataframe(dd[["servicio", "estacion", "llegada", "salida"]],
                         use_container_width=True, hide_index=True, height=520)
        st.caption("Tabla descargable con el ícono de la esquina superior derecha de la tabla.")

# ---------- Marey L2 ----------
with tabs[2]:
    st.subheader("Diagrama de Marey — Línea 2 (Concepción ↔ Coronel)")
    tab_marey("L2", "Concepción", "Coronel")

# ---------- Marey L1 ----------
with tabs[3]:
    st.subheader("Diagrama de Marey — Línea 1 (Mercado ↔ Hualqui ↔ Laja)")
    tab_marey("L1", "Mercado", "Laja")

# ---------- Red ----------
with tabs[4]:
    st.subheader("Red de infraestructura (esquema por corredor)")
    arcos = load("red_arcos.csv"); est = load("red_estaciones.csv"); sen = load("red_senales.csv")
    if arcos.empty:
        st.info("Falta red_arcos.csv.")
    else:
        col1, col2 = st.columns(2)
        ver_sig = col1.checkbox("Mostrar señales (OpenTrack)", value=True)
        solo_ppal = col2.checkbox("Solo señales principales (límites de cantón)", value=False)
        xs, ys = [], []
        for _, r in arcos.iterrows():
            xs += [r.x1, r.x2, None]; ys += [r.y1, r.y2, None]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color="#1F3864", width=0.8),
                                 hoverinfo="skip", showlegend=False))
        if not est.empty:
            fig.add_trace(go.Scatter(x=est["x"], y=est["y"], mode="markers+text",
                                     marker=dict(color="#C00000", size=7), text=est["label"],
                                     textposition="top center", textfont=dict(size=8),
                                     hoverinfo="text", showlegend=False))
        if ver_sig and not sen.empty:
            sg = sen[sen["principal"]] if solo_ppal else sen
            for principal, color, nm in [(True, "#2E7D32", "Señal principal"),
                                         (False, "#FF8C00", "Señal distante")]:
                d = sg[sg["principal"] == principal]
                if not d.empty:
                    fig.add_trace(go.Scatter(x=d["x"], y=d["y"], mode="markers",
                                             marker=dict(color=color, size=5, symbol="triangle-up"),
                                             name=nm, hovertext=d["tipo"], hoverinfo="text"))
        anns = [dict(x=g[["x1", "x2"]].min().min(), y=g["y1"].median(), text=n, showarrow=False,
                     xanchor="right", font=dict(color="#C00000", size=11))
                for n, g in arcos.groupby("nombre")] if "nombre" in arcos.columns else []
        fig.update_layout(height=820, margin=dict(l=10, r=10, t=10, b=10),
                          yaxis=dict(visible=False), xaxis=dict(visible=False), annotations=anns,
                          legend=dict(orientation="h", y=1.02))
        st.plotly_chart(fig, use_container_width=True)
        if not sen.empty:
            st.caption(f"Señales OpenTrack: {len(sen)} ({int(sen['principal'].sum())} principales). "
                       "Un cantón (block) es el tramo entre dos señales PRINCIPALES consecutivas. "
                       "OpenTrack exporta las señales, no los cantones como objeto; estos se derivan "
                       "de las señales principales.")
        blo = load("bloques.csv")
        if not blo.empty:
            with st.expander("Cantones derivados de las señales (alimentan el simulador)"):
                ln = st.radio("Línea", ["L2", "L1"], horizontal=True, key="canton_linea")
                g = blo[blo.linea == ln].copy()
                st.write(f"{len(g)} cantones — {(g.tipo=='single').sum()} en vía única. "
                         "Columna 'limite': si el borde inferior viene de una señal real o de una estación.")
                st.dataframe(g[["block_id", "nombre", "dist_lo", "dist_hi", "longitud_m",
                                "tipo", "limite"]], use_container_width=True, hide_index=True)

# ---------- Mapa ----------
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

# ---------- Optimización ----------
with tabs[6]:
    st.subheader("Optimización de capacidad y flota — hora punta (Etapa 2)")
    res = load_json("optim_resumen.json"); fr = load("optim_frecuencias.csv")
    if res:
        c1, c2, c3 = st.columns(3)
        c1.metric("Cobertura demanda punta", f"{res['cobertura_pct']}%")
        c2.metric("Flota pico usada", f"{res['flota_pico_usada']} / {res['flota_total']}")
        c3.metric("¿Flota suficiente?", "Sí" if res.get("flota_suficiente") else "No")
        sens = res.get("sensibilidad_peak_share")
        if sens:
            st.plotly_chart(px.line(pd.DataFrame(sens), x="peak_share", y="flota_pico", markers=True,
                                    labels={"peak_share": "Factor hora punta", "flota_pico": "Flota pico"}),
                            use_container_width=True)
    if not fr.empty:
        st.dataframe(fr, use_container_width=True, hide_index=True)

# ---------- Material rodante ----------
with tabs[7]:
    st.subheader("Flota Biotren")
    mr = load("material_rodante.csv")
    if not mr.empty:
        st.dataframe(mr[mr["flota_biotren"]], use_container_width=True, hide_index=True)

# ---------- Demanda OD ----------
with tabs[8]:
    st.subheader("Demanda OD por franja")
    od = load("od_franjas.csv")
    if not od.empty:
        st.bar_chart(od.groupby("franja")["viajes"].sum())

# ---------- Perfil de carga ----------
with tabs[9]:
    st.subheader("Perfil de carga por servicio (pasajeros)")
    perfil = load("perfil_carga.csv")
    if not perfil.empty:
        st.dataframe(perfil.sort_values("afluencia", ascending=False),
                     use_container_width=True, hide_index=True)
