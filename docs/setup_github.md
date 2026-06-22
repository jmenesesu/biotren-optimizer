# Subir a GitHub y desplegar en Streamlit Community Cloud

El repositorio ya esta listo (codigo + datos limpios + app). Estos pasos se
ejecutan en tu equipo, en una terminal, dentro de la carpeta `biotren-optimizer`.

## 1. Subir a GitHub

Crea un repositorio vacio en https://github.com/new (ej.: `biotren-optimizer`),
SIN README ni .gitignore. Luego:

```bash
cd "C:\2 Export\biotren-optimizer"
git init
git add .
git commit -m "Biotren optimizer: parsers, motor, optimizador y app con Marey + mapa"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/biotren-optimizer.git
git push -u origin main
```

Si usas GitHub CLI:

```bash
cd "C:\2 Export\biotren-optimizer"
git init && git add . && git commit -m "Biotren optimizer"
gh repo create biotren-optimizer --private --source=. --push
```

## 2. Desplegar la app en Streamlit Community Cloud

1. Entra a https://share.streamlit.io e inicia sesion con tu cuenta de GitHub.
2. "Create app" -> "Deploy a public app from GitHub".
3. Selecciona:
   - Repository: `TU_USUARIO/biotren-optimizer`
   - Branch: `main`
   - Main file path: `app/streamlit_app.py`
4. "Deploy". La primera vez tarda 1-3 min en instalar dependencias.

La app usa `requirements.txt` (ligero: streamlit, pandas, plotly) y lee los datos
de `datos/clean/`, que estan versionados. No necesita los insumos crudos.

## 3. Reemplazar las coordenadas aproximadas del mapa

El mapa usa `datos/clean/estaciones_geo.csv`. La version actual trae coordenadas
APROXIMADAS de L2 (marcadas como "aproximada"). Para usar tus datos reales:

- Exporta desde tu GIS un CSV con columnas: `estacion, linea, lat, lon` (y
  opcionalmente `km`, `fuente`).
- Reemplaza `datos/clean/estaciones_geo.csv` con ese archivo.
- `git add`, `git commit`, `git push`. Streamlit Cloud se actualiza solo.

## 4. Actualizar la app despues de cambios

Cada vez que hagas `git push` a `main`, Streamlit Cloud vuelve a desplegar.
Para regenerar los datos tras cambiar un insumo:

```bash
pip install -r requirements-dev.txt
python run_all.py
git add datos/clean && git commit -m "actualiza datos" && git push
```
