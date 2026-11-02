"""Entrena y compara todos los modelos, y guarda el mejor para la API.

Uso::

    python -m src.modelos.entrenar           # incluye el MLP
    python -m src.modelos.entrenar --sin-mlp
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import date
from pathlib import Path

import pandas as pd
from sklearn.metrics import confusion_matrix
from sklearn.model_selection import GroupShuffleSplit

from src.ingesta.generador import ruta_datos
from src.modelos.base import CATEGORICAS, NUMERICAS, OBJETIVO, ModeloBase, metricas
from src.modelos.clasicos import ModeloSklearn, modelos_clasicos

RAIZ = Path(__file__).resolve().parents[2]


def cargar_dataset(ruta: Path) -> pd.DataFrame:
    """Lee el dataset de modelado que produce ``spark_etl`` y fija los tipos."""
    df = pd.read_parquet(ruta)
    df["cruza_asueto"] = df["cruza_asueto"].astype(int)
    df[OBJETIVO] = df[OBJETIVO].astype(int)
    return df


def dividir(df: pd.DataFrame, prueba: float = 0.2):
    """Separa entrenamiento y prueba por estudiante (ningún estudiante en ambos)."""
    tr, te = next(GroupShuffleSplit(n_splits=1, test_size=prueba, random_state=42)
                  .split(df, df[OBJETIVO], df["numero_estudiante"]))
    return df.iloc[tr].reset_index(drop=True), df.iloc[te].reset_index(drop=True)


def analizar_errores(modelo: ModeloBase, prueba: pd.DataFrame) -> pd.DataFrame:
    """Métricas del modelo por subgrupo: modalidad, historial vacío y tipo de tarea."""
    prob = modelo.predecir_proba(prueba[CATEGORICAS + NUMERICAS])
    prueba = prueba.assign(prob=prob, sin_historial=prueba["hist_n_previas"] == 0)
    filas = []
    for columna in ("modalidad", "sin_historial", "tipo_tarea"):
        for valor, g in prueba.groupby(columna, observed=True):
            if g[OBJETIVO].nunique() < 2:
                continue
            filas.append({"grupo": columna, "valor": str(valor), "n": len(g),
                          "tasa_real": round(g[OBJETIVO].mean(), 3),
                          **{k: round(v, 3) for k, v in metricas(g[OBJETIVO], g["prob"], modelo.umbral).items()}})
    return pd.DataFrame(filas)


def main() -> None:
    """Entrena, compara, analiza errores y guarda artefactos y reportes."""
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--sin-mlp", action="store_true")
    args = p.parse_args()

    df = cargar_dataset(ruta_datos() / "processed" / "dataset_modelo.parquet")
    entreno, prueba = dividir(df)
    X_tr, y_tr, g_tr = entreno[CATEGORICAS + NUMERICAS], entreno[OBJETIVO], entreno["numero_estudiante"]
    X_te, y_te = prueba[CATEGORICAS + NUMERICAS], prueba[OBJETIVO]
    print(f"Entrenamiento: {len(entreno):,} filas · Prueba: {len(prueba):,} filas · "
          f"tasa tardía {y_tr.mean():.3f}", flush=True)

    modelos: list[ModeloBase] = modelos_clasicos()
    if not args.sin_mlp:
        from src.modelos.red_neuronal import ModeloMLP
        modelos.append(ModeloMLP())

    filas = []
    for modelo in modelos:
        inicio = time.perf_counter()
        modelo.entrenar(X_tr, y_tr, g_tr)
        segundos = time.perf_counter() - inicio
        fila = {**modelo.evaluar(X_te, y_te), "segundos_entreno": round(segundos, 1),
                "cv_f1": getattr(modelo, "cv_f1", None),
                "parametros": json.dumps(getattr(modelo, "mejores_parametros", {}))}
        filas.append(fila)
        print({k: (round(v, 4) if isinstance(v, float) else v) for k, v in fila.items()}, flush=True)

    tabla = pd.DataFrame(filas).sort_values("f1", ascending=False)
    (RAIZ / "reports" / "figures").mkdir(parents=True, exist_ok=True)
    tabla.round(4).to_csv(RAIZ / "reports" / "metricas_modelos.csv", index=False)

    # El servicio usa el mejor modelo de scikit-learn: no necesita TensorFlow en la imagen Docker.
    clasicos = [m for m in modelos if isinstance(m, ModeloSklearn) and m.nombre != "baseline"]
    mejor = max(clasicos, key=lambda m: tabla.set_index("modelo").loc[m.nombre, "f1"])
    mejor.guardar(RAIZ / "models" / "modelo_ate.joblib")
    analizar_errores(mejor, prueba).to_csv(RAIZ / "reports" / "analisis_errores.csv", index=False)
    cm = confusion_matrix(y_te, mejor.predecir(X_te))
    metadatos = {"modelo": mejor.nombre, "umbral": mejor.umbral, "version": "0.2.0",
                 "entrenado": date.today().isoformat(), "categoricas": CATEGORICAS, "numericas": NUMERICAS,
                 "metricas_prueba": {k: round(v, 4) for k, v in tabla.set_index("modelo").loc[mejor.nombre].items()
                                     if isinstance(v, float)},
                 "matriz_confusion": cm.tolist(), "filas_entreno": len(entreno), "filas_prueba": len(prueba)}
    (RAIZ / "models" / "modelo_ate.json").write_text(json.dumps(metadatos, indent=2, ensure_ascii=False),
                                                     encoding="utf-8")

    for modelo in modelos:
        if modelo.nombre == "mlp_keras":
            modelo.graficar_curvas(RAIZ / "reports" / "figures" / "curvas_mlp.png")
            modelo.guardar(RAIZ / "models")
            pd.DataFrame(modelo.historia).to_csv(RAIZ / "reports" / "historia_mlp.csv", index_label="epoca")
    print(tabla.drop(columns="parametros").round(4).to_string(index=False))
    print("Mejor modelo para la API:", mejor)


if __name__ == "__main__":
    main()
