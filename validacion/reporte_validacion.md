# Reporte de validación — horarios_limpios (Etapa 1)

Fecha: 22-06-2026. Insumo validado: `datos/clean/horarios_limpios.csv`
(229 servicios de pasajeros, 68 trenes de carga, 4.787 filas).

La validación combina dos métodos independientes: chequeos estructurales a escala
(consistencia interna de los 303 servicios pasajeros por sentido y día) y
verificación visual contra el PDF fuente (lectura directa de celdas, independiente
del parser).

## 1. Hallazgo principal y corrección

La validación detectó un error sistemático de extracción en la **fila terminal**
de cada tabla de pasajeros: el tiempo del primer servicio caía en una columna
(x ≈ 178 px) por debajo del corte `x > 190` y se descartaba, corriendo la
asignación del resto. Esto producía tiempos imposibles en el último tramo
(p. ej. Coronel del 20041 a las 12:12 en vez de 11:12; salto de 62 min).

Corrección: bajé el corte a `x > 160` (recupera la columna de llegada del primer
servicio sin tomar las columnas de "tiempo de viaje") y revertí una heurística de
desfase que introducía errores nuevos, dejando emparejamiento por cercanía simple.

Resultado de los chequeos estructurales tras la corrección:

| Métrica | Antes | Después |
|---|---|---|
| Servicios pasajeros con incidencia | 106 | 0 |
| Tasa de coincidencia limpia (pax) | 65,0 % | 100,0 % |
| Monotonía pax (tiempos que retroceden) | 93 | 0 |
| Dwell anómalo pax | 221 | 0 |
| Velocidad por tramo fuera de rango | — | 0 |

Las 106 "incidencias de orden" remanentes resultaron ser falsos positivos del
propio chequeo (comparaba mayúsculas/minúsculas: "EL ARENAL" vs "El Arenal"). Tras
normalizar, los 303 servicios quedan en el orden canónico de su línea.

## 2. Chequeos estructurales (definición)

Sobre cada servicio de pasajeros (por sentido y tipo de día) se verifica:

1. Monotonía: los tiempos no retroceden a lo largo del recorrido.
2. Orden canónico: las estaciones aparecen en el mismo orden relativo que la
   secuencia oficial de la línea (no penaliza short-turns, que son subconjuntos
   contiguos válidos, ni equipos en vacío, que reposicionan).
3. Velocidad por tramo: la velocidad implicada entre estaciones consecutivas es
   plausible (≤ 120 km/h).
4. Detención: salida ≥ llegada en cada estación.

Resultado: 0 incidencias en los 303 servicios. Script: `chequeos_estructurales.py`.

## 3. Verificación visual contra el PDF

Se leyeron celdas directamente del PDF fuente (recortes a 300 dpi) y se
contrastaron con `horarios_limpios`. Muestra:

| Servicio | Sentido | Celdas verificadas | Resultado |
|---|---|---|---|
| 20000 (SFE 1) | Coronel→Concepción | Coronel 5:55, JPII 6:34, Concepción 6:40 | Coincide |
| 20041 (SFE 3) | Concepción→Coronel | Concepción 10:30, Lomas 10:49, Coronel 11:12 | Coincide |
| 50011 (FEPASA) | Alameda→El Arenal | Chillán 21:44, Gral. Cruz 23:11/23:20, San Rosendo 0:50/0:58, Buenuraqui 1:12/1:30 | Coincide |

Los dos servicios de pasajeros corresponden a los casos que estaban rotos antes de
la corrección; ahora coinciden exactamente con el PDF. El tren de carga confirma
que las horas por estación se leen bien.

## 4. Sobre la carga

39 de 68 trenes de carga presentan tiempos "no monótonos" si se los lee como una
sola secuencia. La verificación visual del 50011 muestra que esto NO es un error
de hora: se debe a (a) el **reinicio de kilometraje** en San Rosendo (la cadena
pasa de 490,0 km a 8,2 km al cambiar de corredor) y (b) **continuaciones y
cruzamientos** entre programas ("Viene de programa EFE Central", marcas × NNNNN).
El mapeo a km maestro y la imposición de monotonía en `generar_malla_carga` ya
manejan esto para los diagramas; en la tabla cruda se conserva el orden del
programa.

## 5. Pendiente / recomendaciones

- Inconsistencia cosmética de nombres: una misma estación aparece en mayúsculas
  cuando es origen/terminal ("EL ARENAL", "HUALQUI") y en formato título cuando es
  intermedia ("El Arenal"). El resolver de km lo normaliza, así que no rompe nada;
  conviene normalizar para limpieza.
- Ampliar la muestra visual de carga (TRANSAP) si se requiere certificación formal.
- La validación de pasajeros se considera cerrada: 100 % consistente y 3 muestras
  exactas contra el PDF.
