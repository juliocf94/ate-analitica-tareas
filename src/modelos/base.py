"""Contrato común de los modelos (patrón Strategy) y métricas compartidas."""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
import pandas as pd
from sklearn.metrics import (accuracy_score, average_precision_score, f1_score, precision_score,
                             recall_score, roc_auc_score)

#: Variables de entrada del modelo. Se excluyen el número de estudiante y el
#: centro (identificadores) y la calificación de la propia tarea, que solo se
#: conoce después de la entrega y filtraría el resultado (fuga de datos).
CATEGORICAS = ["distrito", "grado", "modalidad", "turno", "materia", "tipo_tarea", "prioridad"]
NUMERICAS = ["dias_plazo_habiles", "cruza_asueto", "mes", "dia_semana", "hist_n_previas",
             "hist_tasa_tardia", "hist_promedio_nota", "tasa_tardia_docente"]
OBJETIVO = "entrega_tardia"


def metricas(y_real, probabilidad, umbral: float = 0.5) -> dict:
    """Métricas para la clase positiva «tardía».

    Args:
        y_real: Etiquetas reales (0 o 1).
        probabilidad: Probabilidad estimada de entrega tardía.
        umbral: Corte para convertir la probabilidad en etiqueta.

    Returns:
        F1, precisión, exhaustividad, AUC ROC, AUC PR y exactitud.
    """
    y_pred = (np.asarray(probabilidad) >= umbral).astype(int)
    return {
        "f1": f1_score(y_real, y_pred, zero_division=0),
        "precision": precision_score(y_real, y_pred, zero_division=0),
        "exhaustividad": recall_score(y_real, y_pred, zero_division=0),
        "auc_roc": roc_auc_score(y_real, probabilidad),
        "auc_pr": average_precision_score(y_real, probabilidad),
        "exactitud": accuracy_score(y_real, y_pred),
    }


class ModeloBase(ABC):
    """Contrato común para todos los modelos del proyecto.

    Cada subclase es una estrategia intercambiable: el código de entrenamiento y
    la API solo usan ``entrenar``, ``predecir_proba`` y ``evaluar``.

    Args:
        nombre: Nombre corto del modelo en los reportes.
        umbral: Probabilidad a partir de la cual se marca riesgo de entrega tardía.
    """

    def __init__(self, nombre: str, umbral: float = 0.5) -> None:
        self._nombre = nombre
        self._umbral = umbral
        self._entrenado = False

    @property
    def nombre(self) -> str:
        """Nombre del modelo."""
        return self._nombre

    @property
    def umbral(self) -> float:
        """Umbral de decisión."""
        return self._umbral

    @property
    def entrenado(self) -> bool:
        """True después de llamar a :meth:`entrenar`."""
        return self._entrenado

    @abstractmethod
    def entrenar(self, X: pd.DataFrame, y: pd.Series, grupos: pd.Series | None = None) -> "ModeloBase":
        """Ajusta el modelo; ``grupos`` (estudiantes) se usa en la validación cruzada."""

    @abstractmethod
    def _probabilidades(self, X: pd.DataFrame) -> np.ndarray:
        """Probabilidad de la clase positiva para cada fila."""

    def predecir_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Probabilidad de entrega tardía.

        Raises:
            RuntimeError: Si el modelo no ha sido entrenado.
        """
        if not self._entrenado:
            raise RuntimeError(f"El modelo {self._nombre!r} no ha sido entrenado")
        return self._probabilidades(X)

    def predecir(self, X: pd.DataFrame) -> np.ndarray:
        """Etiqueta 1 (riesgo de entrega tardía) o 0 según :attr:`umbral`."""
        return (self.predecir_proba(X) >= self._umbral).astype(int)

    def evaluar(self, X: pd.DataFrame, y: pd.Series) -> dict:
        """Calcula :func:`metricas` sobre ``X`` e ``y``."""
        return {"modelo": self._nombre, **metricas(y, self.predecir_proba(X), self._umbral)}

    def __repr__(self) -> str:
        estado = "entrenado" if self._entrenado else "sin entrenar"
        return f"{self.__class__.__name__}(nombre={self._nombre!r}, umbral={self._umbral}, {estado})"
