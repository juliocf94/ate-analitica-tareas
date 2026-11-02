"""Prueba del historial con PySpark: la ventana no debe mirar resultados aún desconocidos (HU-07).

Se omite si no hay un JDK disponible (Spark necesita Java).
"""
import os
import shutil
from datetime import datetime

import pytest

pytest.importorskip("pyspark")
if not (os.environ.get("JAVA_HOME") or shutil.which("java")):
    pytest.skip("Spark necesita un JDK (JAVA_HOME)", allow_module_level=True)


@pytest.fixture(scope="module")
def spark():
    from src.ingesta.spark_etl import crear_sesion
    sesion = crear_sesion("ate-pruebas", memoria="1g")
    yield sesion
    sesion.stop()


def _fila(id_, estudiante, dia, tardia, docente="D001"):
    return {"id_entrega": id_, "numero_estudiante": estudiante, "centro": "C001", "distrito": "Apopa",
            "grado": "7°", "modalidad": "regular", "turno": "matutino", "materia": "Ciencias",
            "docente": docente, "tipo_tarea": "tarea", "prioridad": "media", "dias_plazo_habiles": 3,
            "cruza_asueto": False, "fecha_asignacion": datetime(2026, 3, dia),
            "estado": "tardia" if tardia else "entregada", "calificacion": 6.0 if tardia else 9.0,
            "entrega_tardia": float(tardia)}


def test_ventana_solo_usa_el_pasado_conocido(spark):
    from src.ingesta.spark_etl import construir_historial

    filas = [_fila("A1", "E0000001", 2, 1), _fila("A2", "E0000001", 10, 0),
             _fila("A3", "E0000001", 30, 0), _fila("B1", "E0000002", 2, 0)]
    resultado = {r["id_entrega"]: r for r in construir_historial(spark.createDataFrame(filas)).collect()}
    # A2 está a 8 días de A1: el resultado de A1 aún podía no conocerse, así que no cuenta.
    assert resultado["A2"]["hist_n_previas"] == 0 and resultado["A2"]["hist_tasa_tardia"] is None
    # A3 está a 28 días de A1 y a 20 de A2: solo A1 queda fuera del desfase de 21 días.
    assert resultado["A3"]["hist_n_previas"] == 1 and resultado["A3"]["hist_tasa_tardia"] == 1.0
    # La tasa por docente se une a todas las filas del mismo docente.
    assert resultado["B1"]["tasa_tardia_docente"] == pytest.approx(0.25)
