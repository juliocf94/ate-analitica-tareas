"""Pruebas del calendario escolar salvadoreño (HU-17)."""
from datetime import date

import pytest

from src.utils.calendario import CalendarioEscolar


def test_dia_de_difuntos_no_es_dia_de_clase():
    cal = CalendarioEscolar()
    assert not cal.es_dia_de_clase(date(2026, 11, 2), "regular")
    assert cal.es_dia_de_clase(date(2026, 11, 3), "regular")


def test_plazo_salta_vacaciones_agostinas():
    # Viernes 31 de julio + 1 día hábil: del 1 al 6 de agosto no hay clases.
    assert CalendarioEscolar().sumar_dias_habiles(date(2026, 7, 31), 1, "regular") == date(2026, 8, 7)


def test_centro_configura_sus_propios_asuetos():
    # Fiestas patronales de un distrito: solo afectan al centro que las declara.
    patronales = date(2026, 7, 24)
    propio, otro = CalendarioEscolar("San Miguel"), CalendarioEscolar("San Miguel")
    propio.agregar_dia_sin_clases([patronales])
    assert not propio.es_dia_de_clase(patronales, "regular")
    assert otro.es_dia_de_clase(patronales, "regular")
    assert propio.sumar_dias_habiles(date(2026, 7, 23), 1, "regular") == date(2026, 7, 27)


def test_fin_de_semana_cuenta_sabado_y_domingo():
    cal = CalendarioEscolar()
    assert cal.es_dia_de_clase(date(2026, 10, 24), "fin_de_semana")        # sábado
    assert not cal.es_dia_de_clase(date(2026, 10, 26), "fin_de_semana")    # lunes
    assert not cal.es_dia_de_clase(date(2026, 10, 24), "regular")


def test_modalidad_desconocida_y_plazo_invalido():
    cal = CalendarioEscolar()
    with pytest.raises(ValueError, match="Modalidad"):
        cal.es_dia_de_clase(date(2026, 10, 26), "intensiva")
    with pytest.raises(ValueError):
        cal.sumar_dias_habiles(date(2026, 10, 26), 0, "regular")
