"""Historial de cada estudiante con PySpark (modo local): uniones y funciones de ventana.

Calcula, para cada tarea, cómo le fue al estudiante en las tareas anteriores
cuyo resultado ya se conocía. Esas variables alimentan el modelo de riesgo.

Uso::

    python -m src.ingesta.spark_etl --fraccion 0.04
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from src.ingesta.base import EtapaPipeline
from src.ingesta.generador import ruta_datos

RAIZ = Path(__file__).resolve().parents[2]

#: Desfase de la ventana: solo se usan tareas asignadas al menos 21 días antes.
#: El plazo más largo es de 10 días hábiles y puede cruzar una semana de
#: vacaciones; así el resultado de esas tareas ya se conocía (evita fuga de datos).
DESFASE_DIAS = 21

COLUMNAS_MODELO = ["id_entrega", "numero_estudiante", "centro", "distrito", "grado", "modalidad",
                   "turno", "materia", "tipo_tarea", "prioridad", "dias_plazo_habiles", "cruza_asueto",
                   "mes", "dia_semana", "hist_n_previas", "hist_tasa_tardia", "hist_promedio_nota",
                   "tasa_tardia_docente", "entrega_tardia"]


def crear_sesion(nombre: str = "ate-etl", memoria: str | None = None):
    """Crea una SparkSession local con todos los núcleos.

    Args:
        nombre: Nombre de la aplicación en la interfaz de Spark.
        memoria: Memoria del driver (en modo local el driver es el único proceso);
            por defecto ``ATE_SPARK_MEMORY`` o ``2g``.

    Returns:
        La sesión de Spark.
    """
    from pyspark.sql import SparkSession

    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    memoria = memoria or os.environ.get("ATE_SPARK_MEMORY", "2g")
    return (SparkSession.builder.master("local[*]").appName(nombre)
            .config("spark.driver.memory", memoria)
            .config("spark.sql.shuffle.partitions", "16")
            .config("spark.sql.execution.arrow.pyspark.enabled", "true")
            .config("spark.ui.showConsoleProgress", "false")
            .getOrCreate())


def en_muestra(fraccion: float):
    """Columna booleana que elige de forma determinista una fracción de estudiantes.

    Usa un *hash* del número de estudiante: el mismo estudiante cae siempre del
    mismo lado, aunque los datos se procesen por lotes.
    """
    from pyspark.sql import functions as F

    return (F.abs(F.hash("numero_estudiante")) % 10_000) < int(fraccion * 10_000)


def conteos_docente(df, excluir_fraccion: float | None = None):
    """Entregas cerradas y tardías por docente (cada docente da una materia en un centro).

    Args:
        df: Entregas limpias.
        excluir_fraccion: Si se indica, no cuenta a los estudiantes de la muestra de
            modelado, para que entrenamiento y prueba no vean su propia variable objetivo.
    """
    from pyspark.sql import functions as F

    base = df.filter(F.col("estado") != "pendiente")
    if excluir_fraccion:
        base = base.filter(~en_muestra(excluir_fraccion))
    return base.groupBy("docente").agg(F.sum("entrega_tardia").alias("tardias"),
                                       F.count("entrega_tardia").alias("cerradas"))


def construir_historial(df, docentes=None):
    """Añade variables de historial con ventanas y una unión por docente.

    Todo es perezoso: nada se ejecuta hasta que se llama a una acción.

    Args:
        df: DataFrame de Spark con las entregas limpias.
        docentes: Resultado de :func:`conteos_docente`; si es None se calcula con ``df``.

    Returns:
        DataFrame de Spark con las columnas de :data:`COLUMNAS_MODELO`.
    """
    from pyspark.sql import Window
    from pyspark.sql import functions as F

    df = df.withColumn("dia", F.datediff(F.col("fecha_asignacion"), F.lit("2026-01-01")))
    cerradas = F.when(F.col("estado") != "pendiente", 1)
    # Ventana por estudiante ordenada por día de asignación, solo con el pasado conocido.
    pasado = (Window.partitionBy("numero_estudiante").orderBy("dia")
              .rangeBetween(Window.unboundedPreceding, -DESFASE_DIAS))
    df = (df.withColumn("hist_n_previas", F.count(cerradas).over(pasado))
            .withColumn("hist_tasa_tardia", F.avg("entrega_tardia").over(pasado))
            .withColumn("hist_promedio_nota", F.avg("calificacion").over(pasado)))

    # Tasa por docente, calculada en una tabla aparte y unida con broadcast (es pequeña).
    docentes = conteos_docente(df) if docentes is None else docentes
    tasa = docentes.select("docente", (F.col("tardias") / F.col("cerradas")).alias("tasa_tardia_docente"))
    df = df.join(F.broadcast(tasa), on="docente", how="left")

    return (df.withColumn("mes", F.month("fecha_asignacion"))
              .withColumn("dia_semana", F.dayofweek("fecha_asignacion"))
              .select(*COLUMNAS_MODELO))


#: Columnas que se leen de las entregas limpias.
COLUMNAS_ENTRADA = ["id_entrega", "numero_estudiante", "centro", "distrito", "grado", "modalidad", "turno",
                    "materia", "docente", "tipo_tarea", "prioridad", "fecha_asignacion", "dias_plazo_habiles",
                    "cruza_asueto", "estado", "calificacion", "entrega_tardia"]


def _liberar(spark) -> None:
    """Libera los lotes ya procesados.

    Cada lote creado desde Pandas vive en la memoria del *driver* hasta que Python
    suelta la referencia y Spark limpia el RDD; sin forzarlo, con 1 o 2 GB de
    *heap* el proceso se queda sin memoria a mitad del recorrido.
    """
    import gc

    gc.collect()
    spark.sparkContext._jvm.System.gc()


class HistorialSpark(EtapaPipeline):
    """Lee las entregas limpias en Parquet y produce el dataset del modelo.

    Spark calcula las ventanas sobre todo el volumen; después se toma una muestra
    determinista de estudiantes para entrenar (los modelos no necesitan 10 M de
    filas y el MLP debe caber en la memoria de una laptop).

    En Linux (o Docker) Spark lee la carpeta con ``spark.read.parquet``. En Windows
    sin ``winutils.exe`` el sistema de archivos de Hadoop no funciona, así que cada
    archivo se lee con Pandas y se entrega a Spark por Arrow. El resultado es el
    mismo porque el generador escribe a cada estudiante en un solo archivo.

    Args:
        origen: Carpeta Parquet que escribe :class:`src.ingesta.dask_pipeline.LimpiezaDask`.
        destino: Carpeta ``data/processed``.
        fraccion: Fracción de estudiantes que entran en la muestra de modelado.
    """

    def __init__(self, origen: Path, destino: Path, fraccion: float = 0.04) -> None:
        super().__init__("historial_spark")
        self._origen = Path(origen)
        self._destino = Path(destino)
        self._fraccion = fraccion

    def _lotes(self, spark):
        """Devuelve funciones que crean cada lote como DataFrame de Spark (perezoso)."""
        if os.name != "nt":
            return [lambda: spark.read.parquet(str(self._origen)).select(*COLUMNAS_ENTRADA)]
        import pandas as pd

        def cargar(archivo):
            pdf = pd.read_parquet(archivo, columns=COLUMNAS_ENTRADA)
            # Pandas 3 guarda el texto como arreglos Arrow fragmentados que PySpark 4.2 no
            # convierte (``Cannot convert ChunkedArray``) y cae a la vía lenta fila por fila.
            # Con ``object`` la conversión por Arrow funciona.
            for col in pdf.columns:
                if isinstance(pdf[col].dtype, pd.CategoricalDtype) or pd.api.types.is_string_dtype(pdf[col]):
                    pdf[col] = pdf[col].astype(str).astype(object)
            return spark.createDataFrame(pdf)

        return [lambda a=a: cargar(a) for a in sorted(self._origen.glob("*.parquet"))]

    def ejecutar(self, spark=None) -> dict:
        """Ejecuta el ETL y guarda ``dataset_modelo.parquet`` y ``pendientes.parquet``.

        Args:
            spark: Sesión existente; si es None se crea una local.

        Returns:
            Resumen con filas totales, filas de la muestra y segundos por paso.
        """
        import pandas as pd

        propia = spark is None
        spark = spark or crear_sesion()
        try:
            lotes = self._lotes(spark)
            tiempos = {}

            # Paso 1: conteos por docente sin los estudiantes de la muestra (acción: toPandas).
            t = time.perf_counter()
            parciales = []
            for lote in lotes:
                parciales.append(conteos_docente(lote(), self._fraccion).toPandas())
                _liberar(spark)
            conteos = pd.concat(parciales).groupby("docente", as_index=False)[["tardias", "cerradas"]].sum()
            docentes = spark.createDataFrame(conteos)
            tiempos["conteos_docente"] = round(time.perf_counter() - t, 1)

            # Paso 2: ventanas y unión; acciones count() y toPandas() de la muestra.
            t = time.perf_counter()
            total, muestras, plan = 0, [], ""
            for lote in lotes:
                historial = construir_historial(lote(), docentes)
                total += historial.count()
                muestras.append(historial.filter(en_muestra(self._fraccion)).toPandas())
                plan = historial._jdf.queryExecution().simpleString()[:3000]
                historial = None
                _liberar(spark)
            pdf = pd.concat(muestras, ignore_index=True)
            tiempos["historial_y_muestra"] = round(time.perf_counter() - t, 1)

            self._destino.mkdir(parents=True, exist_ok=True)
            # Se escribe con Pandas: en Windows, df.write de Spark también exige winutils.exe.
            pdf[pdf["entrega_tardia"].notna()].to_parquet(self._destino / "dataset_modelo.parquet", index=False)
            pdf[pdf["entrega_tardia"].isna()].to_parquet(self._destino / "pendientes.parquet", index=False)
            return {"lotes": len(lotes), "filas_totales": total, "filas_muestra": len(pdf),
                    "estudiantes_muestra": int(pdf["numero_estudiante"].nunique()),
                    "docentes": len(conteos), "segundos": tiempos,
                    "plan": plan}
        finally:
            if propia:
                spark.stop()


def main() -> None:
    """Punto de entrada de la línea de comandos."""
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--fraccion", type=float, default=0.04)
    args = p.parse_args()
    datos = ruta_datos()
    etapa = HistorialSpark(datos / "processed" / "entregas_limpias", datos / "processed", args.fraccion)
    resumen = etapa.ejecutar_medido()
    plan = resumen.pop("plan")
    print(resumen)
    print(f"{etapa} terminó en {etapa.segundos:.1f} s")
    (RAIZ / "reports").mkdir(exist_ok=True)
    (RAIZ / "reports" / "plan_spark.txt").write_text(plan, encoding="utf-8")


if __name__ == "__main__":
    main()
