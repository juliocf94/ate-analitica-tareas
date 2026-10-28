"""Datos de prueba compartidos. Cada prueba recibe su propia copia (independencia)."""
from datetime import datetime

import pytest

from src.ingesta.generador import GeneradorEntregas


@pytest.fixture
def entregas():
    """Partición sintética pequeña con defectos inyectados (≈2 000 filas)."""
    return GeneradorEntregas(semilla=7, tareas_por_estudiante=100, centros=5).generar_particion(0, 2000)


@pytest.fixture
def documento():
    """Documento de tarea válido para MongoDB."""
    return {
        "id_entrega": "T000-0000001", "numero_estudiante": "E0000001", "centro": "C001", "grado": "7°",
        "seccion": "A", "modalidad": "regular", "materia": "Matemática", "tipo_tarea": "tarea",
        "prioridad": "media", "fecha_asignacion": datetime(2026, 10, 20), "fecha_limite": datetime(2026, 10, 23),
        "estado": "pendiente",
    }
