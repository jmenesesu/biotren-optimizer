"""Pruebas de sanidad de los datasets limpios y del motor de tiempos.

Uso:
    python -m pytest tests/ -q       (o)     python tests/test_parsers.py
"""
import sys
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO / "parsers"))
sys.path.append(str(REPO / "motor"))
from config import CLEAN  # noqa: E402


def test_infra_no_vacia():
    df = pd.read_csv(CLEAN / "infra_edges.csv")
    assert len(df) > 1000
    assert df["edge_length_m"].sum() > 100_000


def test_material_rodante_flota():
    df = pd.read_csv(CLEAN / "material_rodante.csv")
    assert df["flota_biotren"].sum() >= 5
    assert (df["masa_bruta_t"] > 0).all()


def test_od_franjas():
    df = pd.read_csv(CLEAN / "od_franjas.csv")
    assert set(df["franja"]) == {"05-10", "10-16", "16-24"}
    assert (df["viajes"] > 0).all()


def test_perfil_saturacion():
    df = pd.read_csv(CLEAN / "perfil_carga.csv")
    s = df[df["servicio"] == 20008]
    assert not s.empty and bool(s["supera_capacidad"].iloc[0])


def test_motor_tiempo_positivo():
    from running_time import SubTramo, tiempo_recorrido, construir_vehiculo_desde_csv
    dv = pd.read_csv(CLEAN / "material_rodante.csv")
    dc = pd.read_csv(CLEAN / "esfuerzo_tractor.csv")
    veh = construir_vehiculo_desde_csv("SFE-100 normal", dv, dc)
    t, xs, v = tiempo_recorrido([SubTramo(2000, 80, 0.0)], veh)
    assert t > 0
    assert v.max() * 3.6 <= veh.vmax_kmh + 1


def test_perfil_real_y_calibracion():
    from calibrar import calibrar
    cal = calibrar("L2", "CC->CW")[0]
    assert cal["error_medio_abs"] < 0.10
    assert 0.4 <= cal["factor_velocidad_comercial"] <= 1.0


def test_optimizador_capacidad():
    sys.path.append(str(REPO / "optimizador"))
    from optimizar_capacidad import optimizar
    df_fr, res = optimizar()
    assert res["estado"] == "Optimal"
    assert res["cobertura_pct"] >= 99.0
    assert res["flota_pico_usada"] <= 16
    assert "sensibilidad_peak_share" in res
    assert "limitado_por_via_unica" in df_fr.columns


def _run_all():
    fns = [v for k, v in globals().items() if k.startswith("test_")]
    ok = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
            ok += 1
        except Exception as e:
            print(f"FAIL {fn.__name__}: {e}")
    print(f"\n{ok}/{len(fns)} pruebas OK")


if __name__ == "__main__":
    _run_all()
