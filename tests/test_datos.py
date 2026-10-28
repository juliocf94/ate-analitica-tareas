"""Pruebas del generador y de la calidad de los datos tras la limpieza (HU-05, HU-06)."""
import pandas as pd

from src.ingesta.dask_pipeline import DTYPES, agregar, limpiar, limpiar_particion
from src.ingesta.generador import COLUMNAS, GeneradorEntregas


def test_generador_es_determinista():
    a = GeneradorEntregas(semilla=3, tareas_por_estudiante=50).generar_particion(1, 500)
    b = GeneradorEntregas(semilla=3, tareas_por_estudiante=50).generar_particion(1, 500)
    pd.testing.assert_frame_equal(a, b)


def test_columnas_y_reglas_de_fechas(entregas):
    assert list(entregas.columns) == COLUMNAS
    assert (entregas["fecha_limite"] >= entregas["fecha_asignacion"]).all()
    pendientes = entregas["estado"] == "pendiente"
    assert entregas.loc[pendientes, "entrega_tardia"].isna().all()
    assert entregas.loc[~pendientes, "entrega_tardia"].isin([0, 1]).all()


def test_limpieza_corrige_defectos(entregas):
    limpio = limpiar_particion(entregas.astype({k: v for k, v in DTYPES.items() if v != "bool"}))
    assert limpio["id_entrega"].is_unique
    assert len(limpio) < len(entregas)                                  # quitó duplicados
    assert limpio["calificacion"].dropna().between(0, 10).all()        # sin notas fuera de rango
    assert limpio["materia"].notna().all() and not limpio["materia"].str.isupper().any()
    assert pd.api.types.is_datetime64_any_dtype(limpio["fecha_limite"])


def test_agregaciones_dask_coinciden_con_pandas(entregas, tmp_path):
    import dask
    import dask.dataframe as dd

    entregas.to_csv(tmp_path / "entregas_000.csv", index=False)
    ddf = dd.read_csv(str(tmp_path / "entregas_*.csv"), dtype=DTYPES, keep_default_na=False,
                      na_values={"calificacion": [""], "entrega_tardia": [""]})
    perezoso = agregar(limpiar(ddf))["tardia_por_modalidad"]
    con_dask = dask.compute(perezoso)[0].sort_index()
    con_pandas = agregar(limpiar_particion(pd.read_csv(
        tmp_path / "entregas_000.csv", dtype=DTYPES, keep_default_na=False,
        na_values={"calificacion": [""], "entrega_tardia": [""]})))["tardia_por_modalidad"].sort_index()
    pd.testing.assert_frame_equal(con_dask, con_pandas, check_dtype=False)
