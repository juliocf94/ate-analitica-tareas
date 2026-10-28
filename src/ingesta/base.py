"""Contrato común de las etapas del pipeline de datos."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any


class EtapaPipeline(ABC):
    """Etapa del pipeline: recibe una ruta o un DataFrame y devuelve un resultado.

    Las subclases implementan :meth:`ejecutar`; :meth:`ejecutar_medido` añade la
    medición de tiempo que se reporta en ``reports/``.

    Args:
        nombre: Nombre corto de la etapa, usado en los reportes.
    """

    def __init__(self, nombre: str) -> None:
        self._nombre = nombre
        self._segundos: float | None = None

    @property
    def nombre(self) -> str:
        """Nombre de la etapa."""
        return self._nombre

    @property
    def segundos(self) -> float | None:
        """Duración de la última ejecución medida, o None si no se ha medido."""
        return self._segundos

    @abstractmethod
    def ejecutar(self, *args: Any, **kwargs: Any) -> Any:
        """Ejecuta la etapa y devuelve su resultado."""

    def ejecutar_medido(self, *args: Any, **kwargs: Any) -> Any:
        """Ejecuta la etapa y guarda su duración en :attr:`segundos`."""
        inicio = time.perf_counter()
        resultado = self.ejecutar(*args, **kwargs)
        self._segundos = time.perf_counter() - inicio
        return resultado

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(nombre={self._nombre!r})"
