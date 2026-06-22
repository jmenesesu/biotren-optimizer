# Biotren / Corto Laja — Modelo de optimización de itinerarios

Modelo en Python para optimizar los itinerarios de pasajeros de Biotren y Corto
Laja (zona Concepción, EFE Sur) y generar escenarios operacionales optimizados.
La carga (FEPASA, TRANSAP) es una restricción fija; se optimiza el servicio de
pasajeros sobre la red completa (Coronel–Concepción y Mercado–Hualqui–Laja).

Objetivo del modelo: **maximizar la demanda satisfecha** con la flota disponible
(16 unidades), respetando vía única, cruzamientos de carga, cocheras y la
restricción eléctrica por subestación.

## Arquitectura (3 capas)

1. **Motor de tiempos de recorrido** (`motor/`): integra la ecuación de
   movimiento con las curvas de esfuerzo tractor del material rodante; reproduce
   lo que hace OpenTrack pero como insumo, no como optimizador.
2. **Optimizador de servicio** (`optimizador/`, etapas siguientes): MILP que
   decide frecuencias, horarios, destino y rotación de flota.
3. **Validación de conflictos** (etapas siguientes): chequeo de operabilidad en
   vía única y compatibilidad con la carga.

## Estado: Etapa 2 (primer corte del optimizador)

Implementado en esta etapa:

- **Parsers** (`parsers/`) que convierten los insumos crudos en datasets limpios
  (`datos/clean/`): infraestructura, material rodante, matrices OD por franja,
  perfil de carga, tiempos del itinerario y caminos de los trenes de carga.
- **Motor de tiempos** (`motor/running_time.py`) con **perfil real de vía**
  (velocidad límite y gradiente por kilómetro, `motor/corridor_builder.py`), su
  **validación** contra el itinerario (`motor/validar_motor.py`) y su
  **calibración** (`motor/calibrar.py`): tras ajustar un único factor de
  velocidad comercial, el motor reproduce el tiempo del itinerario de L2
  (Concepción–Coronel) con ~2% de error. El resultado se persiste en
  `datos/clean/calibracion.json` para que la optimización use tiempos
  consistentes con el horario.
- **App Streamlit** de exploración (`app/streamlit_app.py`).
- **Pruebas** (`tests/`).

- **Optimizador de capacidad y flota** (`optimizador/`): MILP en PuLP que maximiza
  la demanda satisfecha decidiendo frecuencias por línea y franja, con flota (16),
  intervalo mínimo por vía única y restricción eléctrica por SER. Modela la red como
  árbol (Concepción + ramas Hualqui/Mercado/Coronel). Salidas en
  `datos/clean/optim_frecuencias.csv` y `optim_resumen.json`.

Hallazgos (modelo dimensionado a la HORA PUNTA): con puntas moderadas los 16
automotores alcanzan (8–11 en uso pico); pero la suficiencia es sensible a cuán
aguda sea la punta: con factor de hora punta alto (~0,5, consistente con el
servicio observado de 1.180 pax > 780) la flota queda al límite y aparece demanda
sin servir. La demanda de L2 domina el dimensionamiento; la de L1 es baja.

## Estructura

```
biotren-optimizer/
├── parsers/        # conversión de insumos a datos limpios
├── motor/          # motor de tiempos de recorrido + validación
├── optimizador/    # MILP (etapas siguientes)
├── app/            # interfaz Streamlit
├── datos/
│   ├── raw/        # (vacío; los insumos viven en la carpeta padre)
│   └── clean/      # datasets limpios generados
├── tests/
└── docs/
```

Los insumos crudos (exports OpenTrack, PDFs, Excel) se leen desde la **carpeta
padre** del repositorio (la carpeta de trabajo de EFE Sur). Ver `parsers/config.py`.

## Uso

```bash
pip install -r requirements.txt

# Generar todos los datasets limpios y validar el motor
python run_all.py

# Pruebas
python tests/test_parsers.py

# App con gráficas (diagrama de Marey + mapa georreferenciado)
streamlit run app/streamlit_app.py
```

Para subir a GitHub y desplegar en Streamlit Community Cloud, ver
`docs/setup_github.md`. La app es autónoma (lee `datos/clean/`, versionado).

## Supuestos vigentes (calibrar)

- Capacidad 780 pax/automotor; consumo 200 A; catenaria 3.000 V.
- SER: Escuadrón, Chepe, Quilacoya, Laja (3 MW; Concepción 6 MW).
- Intervalos de vía única: 25 min Hualqui–La Leonera; 9 min Chepe (8 con doble vía).
- Coeficientes de Davis y deceleración de servicio del motor: valores típicos de
  automotor eléctrico, pendientes de calibración con mediciones reales.

Datos pendientes de confirmar: zonas eléctricas por SER, capacidad numérica de
cocheras, tiempos de liberación de bloque. Ver `docs/` y el documento de diseño.

## Próximas etapas

2. (Hecho, primer corte) Optimizador MILP de capacidad y flota.
3. Timetabling fino (salidas minuto a minuto con vía única y carga).
4. Validación de conflictos + despliegue Streamlit del optimizador.
