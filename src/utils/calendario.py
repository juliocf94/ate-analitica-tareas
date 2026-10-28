"""Calendario escolar salvadoreño: asuetos, vacaciones y días de clase por modalidad.

Fuentes: Calendario Escolar 2026 del MINEDUCYT y Art. 190 del Código de Trabajo
(ver docs/decisiones.md y la propuesta del proyecto). Cada centro puede añadir
o quitar fechas con :meth:`CalendarioEscolar.agregar_dia_sin_clases`.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

import numpy as np

#: Modalidades admitidas y días de la semana con clases (0 = lunes ... 6 = domingo).
DIAS_DE_CLASE: dict[str, tuple[int, ...]] = {
    "regular": (0, 1, 2, 3, 4),
    "nocturna": (0, 1, 2, 3, 4),
    "fin_de_semana": (5, 6),
    "a_distancia": (0, 1, 2, 3, 4, 5, 6),
}

#: Asuetos nacionales 2026 (Art. 190 del Código de Trabajo).
ASUETOS_NACIONALES_2026: tuple[date, ...] = (
    date(2026, 1, 1),
    date(2026, 4, 2), date(2026, 4, 3), date(2026, 4, 4),
    date(2026, 5, 1), date(2026, 5, 10), date(2026, 6, 17),
    date(2026, 8, 6), date(2026, 9, 15), date(2026, 11, 2), date(2026, 12, 25),
)

#: Asuetos que solo aplican en un distrito.
ASUETOS_LOCALES_2026: dict[str, tuple[date, ...]] = {
    "San Salvador": (date(2026, 8, 3), date(2026, 8, 5)),
}

#: Vacaciones del calendario escolar 2026 (inicio y fin, ambos incluidos).
VACACIONES_2026: tuple[tuple[date, date], ...] = (
    (date(2026, 3, 29), date(2026, 4, 5)),   # Semana Santa
    (date(2026, 8, 1), date(2026, 8, 6)),    # Fiestas Agostinas
)

INICIO_ANIO_2026 = date(2026, 2, 2)
CIERRE_ANIO_2026 = date(2026, 11, 13)


class CalendarioEscolar:
    """Calendario de un centro educativo para calcular plazos en días hábiles.

    Args:
        distrito: Distrito del centro; decide qué asuetos locales aplican.
        inicio: Primer día del año escolar.
        cierre: Último día del año escolar.

    Example:
        >>> cal = CalendarioEscolar("San Salvador")
        >>> cal.es_dia_de_clase(date(2026, 11, 2), "regular")
        False
    """

    def __init__(self, distrito: str = "", inicio: date = INICIO_ANIO_2026,
                 cierre: date = CIERRE_ANIO_2026) -> None:
        self._distrito = distrito
        self._inicio = inicio
        self._cierre = cierre
        self._sin_clases: set[date] = set(ASUETOS_NACIONALES_2026)
        self._sin_clases.update(ASUETOS_LOCALES_2026.get(distrito, ()))
        for desde, hasta in VACACIONES_2026:
            self._sin_clases.update(desde + timedelta(d) for d in range((hasta - desde).days + 1))

    def __repr__(self) -> str:
        return (f"CalendarioEscolar(distrito={self._distrito!r}, inicio={self._inicio}, "
                f"cierre={self._cierre}, dias_sin_clases={len(self._sin_clases)})")

    def agregar_dia_sin_clases(self, fechas: Iterable[date]) -> None:
        """Marca fechas adicionales sin clases (asuetos propios del centro).

        Args:
            fechas: Fechas que el centro declara sin clases.
        """
        self._sin_clases.update(fechas)

    def es_dia_de_clase(self, dia: date, modalidad: str) -> bool:
        """Indica si ``dia`` cuenta para el plazo en la modalidad dada.

        Args:
            dia: Fecha a evaluar.
            modalidad: Una de las claves de :data:`DIAS_DE_CLASE`.

        Returns:
            True si hay clases ese día para esa modalidad.

        Raises:
            ValueError: Si la modalidad no existe.
        """
        if modalidad not in DIAS_DE_CLASE:
            raise ValueError(f"Modalidad desconocida: {modalidad!r}")
        return (self._inicio <= dia <= self._cierre
                and dia.weekday() in DIAS_DE_CLASE[modalidad]
                and dia not in self._sin_clases)

    def sumar_dias_habiles(self, desde: date, dias: int, modalidad: str) -> date:
        """Devuelve la fecha límite que resulta de contar ``dias`` hábiles desde ``desde``.

        El día de asignación no cuenta. Si el plazo se sale del año escolar,
        se devuelve el último día de clase disponible.

        Args:
            desde: Fecha de asignación.
            dias: Días hábiles de plazo (mayor que cero).
            modalidad: Modalidad de la sección.

        Returns:
            La fecha límite, que siempre es un día de clase.

        Raises:
            ValueError: Si ``dias`` no es positivo.
        """
        if dias <= 0:
            raise ValueError("El plazo debe ser de al menos un día hábil")
        actual, contados, ultimo = desde, 0, None
        while contados < dias and actual < self._cierre:
            actual += timedelta(days=1)
            if self.es_dia_de_clase(actual, modalidad):
                contados += 1
                ultimo = actual
        return ultimo or desde

    def dias_de_clase(self, modalidad: str) -> np.ndarray:
        """Lista ordenada de días de clase del año, como ``datetime64[D]``.

        Args:
            modalidad: Modalidad de la sección.

        Returns:
            Arreglo con todas las fechas de clase entre inicio y cierre.
        """
        total = (self._cierre - self._inicio).days + 1
        dias = [self._inicio + timedelta(d) for d in range(total)]
        return np.array([d for d in dias if self.es_dia_de_clase(d, modalidad)], dtype="datetime64[D]")

    def cruza_dia_sin_clases(self, desde: date, hasta: date) -> bool:
        """Indica si entre dos fechas hay un asueto o un día de vacaciones.

        Args:
            desde: Fecha de asignación.
            hasta: Fecha límite.

        Returns:
            True si algún día del intervalo abierto (desde, hasta) no tiene clases por asueto o vacaciones.
        """
        return any(desde < d < hasta for d in self._sin_clases)
