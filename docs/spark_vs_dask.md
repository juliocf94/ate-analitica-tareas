# Dask frente a PySpark en ATE

Los dos procesan datos que no caben cómodos en memoria, pero resuelven partes distintas del pipeline.

| Aspecto | Dask (`src/ingesta/dask_pipeline.py`) | PySpark (`src/ingesta/spark_etl.py`) |
| --- | --- | --- |
| Qué hace en ATE | Limpia los CSV crudos y calcula las agregaciones del panel | Calcula el historial previo de cada estudiante y une la tasa por docente |
| Modelo de ejecución | Grafo de tareas de Python; `.compute()` lo ejecuta | Plan lógico optimizado por Catalyst; una acción (`count`, `toPandas`) lo ejecuta |
| Perezoso hasta | `dask.compute(...)` | `count()`, `toPandas()`, `write` |
| API | La de Pandas, partición por partición | DataFrames de Spark SQL (`Window`, `join`, `broadcast`) |
| Arranque | Inmediato, mismo proceso de Python | Arranca una JVM (unos segundos) y necesita un JDK |
| Fuerte en | Operaciones por partición (`map_partitions`) y agregaciones | Ventanas, uniones grandes y *shuffles* con optimizador |
| Débil en | Ventanas ordenadas por grupo (requiere reparticionar a mano) | Código de Pandas existente; en Windows leer y escribir exige `winutils.exe` |

## Nota sobre Windows

Spark 4 usa el sistema de archivos de Hadoop, que en Windows necesita `winutils.exe` y `hadoop.dll`.
Sin ellos falla incluso la lectura (`NativeIO$Windows.access0`). En Windows, `HistorialSpark` lee
cada archivo con Pandas y lo pasa a Spark con Arrow (`createDataFrame`); en Linux o Docker lee la
carpeta con `spark.read.parquet`. Las transformaciones son las mismas en ambos casos.

## Transformaciones y acciones

En `HistorialSpark.ejecutar` todo lo que va antes de una acción es perezoso: la lectura,
`withColumn`, las funciones de ventana, el `join` con `broadcast` y el `select` solo construyen el
plan (se guarda en `reports/plan_spark.txt`). Las acciones son tres: `toPandas()` de los conteos
por docente, `count()` del historial completo y `toPandas()` de la muestra de modelado.

En Dask pasa lo mismo: `read_csv`, `map_partitions(limpiar_particion)` y los `groupby` no leen
nada hasta `dask.compute(*agregaciones)`, que comparte la lectura entre las cuatro agregaciones.

## Cuándo conviene cada uno

- **Dask** cuando el trabajo ya está escrito en Pandas, es por partición o es una agregación, y se
  quiere todo en un solo proceso de Python sin JVM.
- **PySpark** cuando hay ventanas por grupo, uniones entre tablas grandes o el volumen crecerá a
  un clúster real: el mismo código corre con `master("yarn")` o en Databricks.

## Mediciones

Ver `reports/tiempos_dask_vs_pandas.csv` y la tabla de la bitácora del Hito II.
