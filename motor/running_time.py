"""Motor de tiempos de recorrido (Capa A).

Integra la ecuación de movimiento de un tren sobre un perfil de vía para
obtener el tiempo mínimo de recorrido entre dos paradas, considerando:
  - Esfuerzo tractor F(v) (curva del material rodante).
  - Resistencia a la marcha (Davis): R = A + B·v + C·v²  [N].
  - Resistencia por gradiente: m·g·(i/1000)  [N], i en por mil.
  - Límites de velocidad por tramo y velocidad máxima del vehículo.
  - Envolvente de frenado hacia la próxima parada (deceleración de servicio).

Método: integración en el espacio con paso ds. Pasada hacia adelante limitada
por tracción y, en paralelo, envolvente de frenado hacia atrás; la velocidad
admisible es el mínimo de ambas y del límite de vía.

Los coeficientes de Davis y la deceleración de servicio son SUPUESTOS
parametrizados (valores típicos de automotor eléctrico) y deben calibrarse
contra mediciones reales. Ver docs/.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple
import numpy as np

G = 9.81  # m/s²


@dataclass
class Vehiculo:
    nombre: str
    masa_t: float                     # masa bruta (t)
    factor_masa_rotante: float        # adimensional (>1)
    vmax_kmh: float
    # curva de esfuerzo tractor: arrays de velocidad (km/h) y esfuerzo (N)
    v_curva_kmh: np.ndarray
    f_curva_n: np.ndarray
    # Davis (N): A + B·v + C·v²  con v en m/s  (supuestos por defecto, calibrables)
    davis_a: float = None
    davis_b: float = None
    davis_c: float = None
    dec_servicio: float = 0.8         # m/s² (supuesto)

    def __post_init__(self):
        m = self.masa_t
        # Davis por defecto (orden de magnitud para EMU); calibrar.
        if self.davis_a is None:
            self.davis_a = 1.5 * m * G * 0.001 * 1000      # ~ 1.5 N/kN * peso
        if self.davis_b is None:
            self.davis_b = 0.033 * m                        # término lineal
        if self.davis_c is None:
            self.davis_c = 0.045 * (self.masa_t / 100.0)    # término aerodinámico

    def esfuerzo(self, v_ms: float) -> float:
        """Esfuerzo tractor disponible (N) a velocidad v (m/s)."""
        v_kmh = v_ms * 3.6
        if v_kmh <= self.v_curva_kmh[0]:
            return float(self.f_curva_n[0])
        if v_kmh >= self.v_curva_kmh[-1]:
            return float(self.f_curva_n[-1])
        return float(np.interp(v_kmh, self.v_curva_kmh, self.f_curva_n))

    def resistencia(self, v_ms: float) -> float:
        return self.davis_a + self.davis_b * v_ms + self.davis_c * v_ms * v_ms


@dataclass
class SubTramo:
    largo_m: float
    vlim_kmh: float
    gradiente_permil: float = 0.0     # positivo = subida en sentido de marcha


def _masa_efectiva_kg(veh: Vehiculo) -> float:
    return veh.masa_t * 1000.0 * veh.factor_masa_rotante


def tiempo_recorrido(perfil: List[SubTramo], veh: Vehiculo,
                     ds: float = 5.0,
                     v_ini_kmh: float = 0.0, v_fin_kmh: float = 0.0
                     ) -> Tuple[float, np.ndarray, np.ndarray]:
    """Tiempo mínimo (s) de recorrer 'perfil' partiendo y terminando en v_ini/v_fin.

    Devuelve (tiempo_s, posiciones_m, velocidades_ms).
    """
    # Discretizar el perfil en puntos cada ds
    xs, vlim, grad = [], [], []
    x = 0.0
    for st in perfil:
        n = max(1, int(round(st.largo_m / ds)))
        paso = st.largo_m / n
        for _ in range(n):
            xs.append(x)
            vlim.append(st.vlim_kmh / 3.6)
            grad.append(st.gradiente_permil)
            x += paso
    xs.append(x)
    vlim.append(min(perfil[-1].vlim_kmh, veh.vmax_kmh) / 3.6)
    grad.append(perfil[-1].gradiente_permil)
    xs = np.array(xs); vlim = np.minimum(np.array(vlim), veh.vmax_kmh / 3.6)
    grad = np.array(grad)
    N = len(xs)
    m = _masa_efectiva_kg(veh)

    # Pasada hacia adelante: aceleración limitada por tracción
    v_fwd = np.zeros(N)
    v_fwd[0] = v_ini_kmh / 3.6
    for i in range(1, N):
        dx = xs[i] - xs[i - 1]
        v = v_fwd[i - 1]
        F = veh.esfuerzo(v)
        R = veh.resistencia(v)
        Fg = m * G * (grad[i - 1] / 1000.0)
        a = (F - R - Fg) / m
        v2 = v * v + 2 * a * dx
        v_next = np.sqrt(v2) if v2 > 0 else 0.0
        v_fwd[i] = min(v_next, vlim[i])

    # Pasada hacia atrás: envolvente de frenado (deceleración de servicio)
    v_bwd = np.zeros(N)
    v_bwd[-1] = v_fin_kmh / 3.6
    dec = veh.dec_servicio
    for i in range(N - 2, -1, -1):
        dx = xs[i + 1] - xs[i]
        v2 = v_bwd[i + 1] ** 2 + 2 * dec * dx
        v_bwd[i] = min(np.sqrt(v2), vlim[i])

    v = np.minimum(np.minimum(v_fwd, v_bwd), vlim)
    v = np.maximum(v, 0.01)  # evitar división por cero

    # Integrar tiempo: dt = dx / v_media
    t = 0.0
    for i in range(1, N):
        dx = xs[i] - xs[i - 1]
        vm = 0.5 * (v[i] + v[i - 1])
        t += dx / max(vm, 0.01)
    return t, xs, v


def construir_vehiculo_desde_csv(nombre_contiene: str, df_veh, df_curva) -> Vehiculo:
    """Crea un Vehiculo a partir de los CSV limpios de material rodante."""
    fila = df_veh[df_veh["nombre"].str.contains(nombre_contiene, regex=False)].iloc[0]
    curva = df_curva[df_curva["vehicle_id"] == fila["vehicle_id"]].sort_values("velocidad_kmh")
    return Vehiculo(
        nombre=fila["nombre"],
        masa_t=float(fila["masa_bruta_t"]),
        factor_masa_rotante=float(fila["factor_masa_rotante"]),
        vmax_kmh=float(fila["vmax_kmh"]),
        v_curva_kmh=curva["velocidad_kmh"].to_numpy(),
        f_curva_n=curva["esfuerzo_n"].to_numpy(),
    )
