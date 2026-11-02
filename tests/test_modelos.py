"""Pruebas de los modelos y del contrato Strategy (HU-10, HU-11)."""
import numpy as np
import pandas as pd
import pytest

from src.modelos.base import CATEGORICAS, NUMERICAS, ModeloBase, metricas
from src.modelos.clasicos import ModeloBaseline, ModeloLogistico, ModeloSklearn


@pytest.fixture
def datos():
    rng = np.random.default_rng(0)
    n = 600
    X = pd.DataFrame({c: rng.choice(["a", "b", "c"], n) for c in CATEGORICAS})
    for c in NUMERICAS:
        X[c] = rng.normal(size=n)
    X.loc[:20, "hist_tasa_tardia"] = np.nan                      # historial vacío
    y = pd.Series((X["dias_plazo_habiles"] + rng.normal(0, 0.5, n) > 0.3).astype(int))
    grupos = pd.Series(np.repeat(np.arange(60), 10))
    return X, y, grupos


def test_no_se_puede_instanciar_la_base():
    with pytest.raises(TypeError):
        ModeloBase("abstracto")


def test_predecir_sin_entrenar_falla(datos):
    X, _, _ = datos
    with pytest.raises(RuntimeError, match="no ha sido entrenado"):
        ModeloLogistico().predecir(X)


def test_estrategias_intercambiables(datos):
    X, y, grupos = datos
    resultados = {m.nombre: m.entrenar(X, y, grupos).evaluar(X, y) for m in (ModeloBaseline(), ModeloLogistico())}
    assert resultados["regresion_logistica"]["f1"] > resultados["baseline"]["f1"]
    assert set(resultados["baseline"]) >= {"f1", "precision", "exhaustividad", "auc_roc"}


def test_pipeline_imputa_y_guarda(datos, tmp_path):
    X, y, _ = datos
    modelo = ModeloLogistico().entrenar(X, y)          # sin grupos: no hay búsqueda
    prob = modelo.predecir_proba(X)
    assert prob.shape == (len(X),) and np.isfinite(prob).all() and ((prob >= 0) & (prob <= 1)).all()
    ruta = modelo.guardar(tmp_path / "m.joblib")
    from src.modelos.clasicos import cargar_pipeline
    assert np.allclose(cargar_pipeline(ruta).predict_proba(X)[:, 1], prob)
    assert "entrenado" in repr(modelo) and isinstance(modelo, ModeloSklearn)


def test_metricas_con_prediccion_perfecta():
    m = metricas([0, 1, 1, 0], [0.1, 0.9, 0.8, 0.2])
    assert m["f1"] == 1.0 and m["auc_roc"] == 1.0
