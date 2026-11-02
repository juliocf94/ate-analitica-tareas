"""Perceptrón multicapa (MLP) con Keras para datos tabulares."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from sklearn.model_selection import GroupShuffleSplit

from src.modelos.base import ModeloBase
from src.modelos.clasicos import crear_preprocesador


class ModeloMLP(ModeloBase):
    """MLP de dos capas ocultas con dropout y parada temprana.

    El preprocesador es el mismo de los modelos clásicos y se ajusta solo con
    la parte de entrenamiento; la validación se separa por estudiante.

    Args:
        capas: Neuronas por capa oculta.
        dropout: Tasa de dropout después de cada capa oculta.
        epocas: Máximo de épocas (la parada temprana suele cortar antes).
        lote: Tamaño de lote.
    """

    def __init__(self, capas: tuple[int, ...] = (64, 32), dropout: float = 0.3, epocas: int = 30,
                 lote: int = 1024) -> None:
        super().__init__("mlp_keras")
        self._capas = capas
        self._dropout = dropout
        self._epocas = epocas
        self._lote = lote
        self._prep = crear_preprocesador(denso=True)
        self._red = None
        self.historia: dict[str, list[float]] = {}

    def _construir(self, entradas: int):
        import keras
        from keras import layers

        keras.utils.set_random_seed(0)
        red = keras.Sequential([keras.Input(shape=(entradas,))])
        for n in self._capas:
            red.add(layers.Dense(n, activation="relu"))
            red.add(layers.Dropout(self._dropout))
        red.add(layers.Dense(1, activation="sigmoid"))
        red.compile(optimizer=keras.optimizers.Adam(1e-3), loss="binary_crossentropy",
                    metrics=[keras.metrics.AUC(name="auc")])
        return red

    def entrenar(self, X, y, grupos=None):
        """Entrena con validación del 15 % de los estudiantes y ``EarlyStopping``."""
        import keras

        if grupos is not None:
            tr, va = next(GroupShuffleSplit(n_splits=1, test_size=0.15, random_state=0).split(X, y, grupos))
        else:
            corte = int(len(X) * 0.85)
            tr, va = np.arange(corte), np.arange(corte, len(X))
        X_tr = self._prep.fit_transform(X.iloc[tr]).astype("float32")
        X_va = self._prep.transform(X.iloc[va]).astype("float32")
        y_tr, y_va = y.iloc[tr].to_numpy(), y.iloc[va].to_numpy()
        positivos = y_tr.mean()
        pesos = {0: 0.5 / (1 - positivos), 1: 0.5 / positivos}       # equivalente a class_weight="balanced"
        self._red = self._construir(X_tr.shape[1])
        parada = keras.callbacks.EarlyStopping(monitor="val_loss", patience=3, restore_best_weights=True)
        h = self._red.fit(X_tr, y_tr, validation_data=(X_va, y_va), epochs=self._epocas,
                          batch_size=self._lote, class_weight=pesos, callbacks=[parada], verbose=0)
        self.historia = {k: [float(v) for v in vals] for k, vals in h.history.items()}
        self._entrenado = True
        return self

    def _probabilidades(self, X):
        return self._red.predict(self._prep.transform(X).astype("float32"), verbose=0, batch_size=8192).ravel()

    def graficar_curvas(self, ruta: str | Path) -> Path:
        """Guarda las curvas de pérdida y AUC de entrenamiento y validación."""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        ruta = Path(ruta)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        fig, ejes = plt.subplots(1, 2, figsize=(10, 4))
        for eje, metrica in zip(ejes, ("loss", "auc")):
            eje.plot(self.historia[metrica], label="entrenamiento", color="#1f5fae")
            eje.plot(self.historia[f"val_{metrica}"], label="validación", color="#9a3412")
            eje.set(title={"loss": "Pérdida (entropía cruzada)", "auc": "AUC ROC"}[metrica], xlabel="Época")
            eje.grid(alpha=0.3)
            eje.legend()
        fig.tight_layout()
        fig.savefig(ruta, dpi=120)
        plt.close(fig)
        return ruta

    def guardar(self, carpeta: str | Path) -> Path:
        """Guarda la red (``mlp_ate.keras``) y el preprocesador (``mlp_prep.joblib``)."""
        import joblib

        carpeta = Path(carpeta)
        carpeta.mkdir(parents=True, exist_ok=True)
        self._red.save(carpeta / "mlp_ate.keras")
        joblib.dump(self._prep, carpeta / "mlp_prep.joblib")
        return carpeta / "mlp_ate.keras"
