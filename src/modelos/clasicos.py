"""Modelos clásicos de scikit-learn, todos dentro de un Pipeline para evitar fuga de datos."""
from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GridSearchCV, StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.svm import LinearSVC

from src.modelos.base import CATEGORICAS, NUMERICAS, ModeloBase


def crear_preprocesador(denso: bool = False) -> ColumnTransformer:
    """Codificación de categóricas e imputación y escalado de numéricas.

    Al vivir dentro del Pipeline, el imputador, el escalador y el codificador se
    ajustan solo con los datos de entrenamiento de cada pliegue.

    Args:
        denso: Si es True la salida es una matriz densa (necesaria para Keras).
    """
    numericas = Pipeline([("imputar", SimpleImputer(strategy="median", add_indicator=True)),
                          ("escalar", StandardScaler())])
    categoricas = OneHotEncoder(handle_unknown="ignore", sparse_output=not denso)
    return ColumnTransformer([("num", numericas, NUMERICAS), ("cat", categoricas, CATEGORICAS)],
                             sparse_threshold=0 if denso else 0.3)


class ModeloSklearn(ModeloBase):
    """Estrategia genérica: preprocesador + estimador de scikit-learn.

    Args:
        nombre: Nombre del modelo.
        estimador: Clasificador de scikit-learn.
        rejilla: Hiperparámetros a explorar con ``GridSearchCV`` (prefijo ``modelo__``).
        muestra_busqueda: Filas máximas usadas en la búsqueda; luego se reentrena con todo.
    """

    def __init__(self, nombre: str, estimador, rejilla: dict | None = None,
                 muestra_busqueda: int = 60_000) -> None:
        super().__init__(nombre)
        self._pipeline = Pipeline([("prep", crear_preprocesador()), ("modelo", estimador)])
        self._rejilla = rejilla or {}
        self._muestra = muestra_busqueda
        self.mejores_parametros: dict = {}
        self.cv_f1: float | None = None

    def entrenar(self, X, y, grupos=None):
        """Busca hiperparámetros con validación cruzada agrupada y ajusta con todo ``X``.

        Los pliegues se agrupan por estudiante: un mismo estudiante nunca está a
        la vez en entrenamiento y validación.
        """
        if self._rejilla and grupos is not None:
            idx = np.random.default_rng(0).permutation(len(X))[: self._muestra]
            busqueda = GridSearchCV(self._pipeline, self._rejilla, scoring="f1", n_jobs=-1,
                                    cv=StratifiedGroupKFold(n_splits=3, shuffle=True, random_state=0))
            busqueda.fit(X.iloc[idx], y.iloc[idx], groups=grupos.iloc[idx])
            self.mejores_parametros = busqueda.best_params_
            self.cv_f1 = float(busqueda.best_score_)
            self._pipeline.set_params(**busqueda.best_params_)
        self._pipeline.fit(X, y)
        self._entrenado = True
        return self

    def _probabilidades(self, X):
        return self._pipeline.predict_proba(X)[:, 1]

    @property
    def pipeline(self) -> Pipeline:
        """Pipeline completo (preprocesador + estimador), listo para serializar."""
        return self._pipeline

    def guardar(self, ruta: str | Path) -> Path:
        """Serializa el Pipeline con joblib."""
        ruta = Path(ruta)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self._pipeline, ruta)
        return ruta


class ModeloBaseline(ModeloSklearn):
    """Línea base trivial: predice al azar respetando la proporción de clases."""

    def __init__(self) -> None:
        super().__init__("baseline", DummyClassifier(strategy="stratified", random_state=0))


class ModeloLogistico(ModeloSklearn):
    """Regresión logística con regularización L2 (lineal, interpretable)."""

    def __init__(self) -> None:
        super().__init__("regresion_logistica",
                         LogisticRegression(max_iter=1000, class_weight="balanced"),
                         {"modelo__C": [0.01, 0.1, 1.0]})


class ModeloBosque(ModeloSklearn):
    """Bosque aleatorio (ensemble de árboles): capta interacciones no lineales."""

    def __init__(self) -> None:
        super().__init__("random_forest",
                         RandomForestClassifier(n_estimators=150, class_weight="balanced_subsample",
                                                n_jobs=-1, random_state=0),
                         {"modelo__max_depth": [8, 14], "modelo__min_samples_leaf": [20, 80]})


class ModeloSVM(ModeloSklearn):
    """SVM lineal calibrada: margen máximo con probabilidades por calibración sigmoide."""

    def __init__(self) -> None:
        super().__init__("svm_lineal",
                         CalibratedClassifierCV(LinearSVC(class_weight="balanced"), cv=3, method="sigmoid"),
                         {"modelo__estimator__C": [0.01, 0.1, 1.0]})


def modelos_clasicos() -> list[ModeloSklearn]:
    """Las estrategias que se comparan, de la más simple a la más flexible."""
    return [ModeloBaseline(), ModeloLogistico(), ModeloSVM(), ModeloBosque()]


def cargar_pipeline(ruta: str | Path):
    """Carga un Pipeline serializado con :meth:`ModeloSklearn.guardar`."""
    return joblib.load(Path(ruta))


def a_dataframe(registros: list[dict]) -> pd.DataFrame:
    """Convierte registros (p. ej., de la API) al DataFrame que espera el Pipeline."""
    return pd.DataFrame(registros, columns=CATEGORICAS + NUMERICAS)
