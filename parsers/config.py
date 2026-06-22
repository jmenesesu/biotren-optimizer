"""Rutas y constantes compartidas por los parsers.

Los insumos crudos viven en la carpeta padre (C:\\2 Export). El repositorio
escribe sus datasets limpios en datos/clean/.
"""
from pathlib import Path

# Raíz del repositorio (este archivo está en parsers/)
REPO = Path(__file__).resolve().parents[1]

# La carpeta de insumos es la carpeta padre del repositorio (C:\\2 Export)
INSUMOS = REPO.parent

# Subcarpetas de insumos
EXPORT_OT = INSUMOS / ".00 Export Opentrack"
INFRA_DIR = EXPORT_OT / "Exchange Infraestructure Data"
RS_DIR = EXPORT_OT / "Exchange Rolling Stock Data"
STA_DIR = EXPORT_OT / "Exchange Station Data"
ITIN_DIR = INSUMOS / "Itinerarios"
PERFIL_DIR = INSUMOS / "25 Perfil de Carga 2026"
MATRIZ_DIR = INSUMOS / "26 Matrices de Viaje Cierre 2025"

# Salida
CLEAN = REPO / "datos" / "clean"
CLEAN.mkdir(parents=True, exist_ok=True)

# Códigos de estación (nomenclatura ferroviaria EFE Sur)
COD_ESTACION = {
    "CW": "Coronel", "CC": "Concepción", "HQ": "Hualqui", "TH": "Mercado",
    "LM": "Lomas Coloradas", "ZW": "La Leonera", "GU": "Desvío Lagunillas",
    "EZ": "El Arenal",
}

# Capacidad de referencia por automotor (pax)
CAP_AUTOMOTOR = 780
# Consumo por automotor en marcha (A) y tensión de alimentación (V)
CONSUMO_A = 200
TENSION_V = 3000
