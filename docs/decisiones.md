# Registro de decisiones

Una entrada por decisión relevante: contexto, alternativas, decisión y consecuencias.

## Decisión 001: un solo backend en Python con FastAPI

Fecha: 2026-10-25 · Estado: aceptada

- **Contexto:** el frontend necesita gestionar tareas y la rúbrica exige una API de predicción.
- **Alternativas:** A) Node.js + Express para las tareas y FastAPI para el modelo. B) Solo FastAPI.
- **Decisión:** B. Un solo servicio atiende las tareas y `/v1/predict`, y todo el código evaluado queda en Python.
- **Consecuencias:** menos piezas que desplegar; el frontend depende de una sola URL.

## Decisión 002: MongoDB como único almacén de la aplicación

Fecha: 2026-10-25 · Estado: aceptada

- **Contexto:** la propuesta inicial combinaba MySQL y MongoDB.
- **Alternativas:** A) MySQL para tareas y MongoDB para seguimiento. B) Solo MongoDB.
- **Decisión:** B. Las tareas y su historial son documentos semiestructurados, y la Práctica NoSQL ya dejó configurado Atlas.
- **Consecuencias:** desarrollo con un MongoDB local y pruebas con mongomock; S3 queda para archivos y artefactos.

## Decisión 003: frontend React como PWA

Fecha: 2026-10-25 · Estado: aceptada

- **Contexto:** las familias usan teléfonos Android, iOS y Huawei (sin Google Play) de gama alta y baja, y las escuelas usan computadoras con navegadores variados.
- **Alternativas:** A) Apps nativas. B) Web adaptable. C) PWA.
- **Decisión:** C. Un solo código se instala desde el navegador en cualquier sistema, sin tiendas de aplicaciones.
- **Consecuencias:** hay que cuidar el peso del paquete y probar en navegadores antiguos.

## Decisión 004: datos sintéticos con reglas documentadas

Fecha: 2026-10-28 · Estado: aceptada

- **Contexto:** la guía prohíbe datos personales reales y ninguna escuela nos puede ceder su historial de entregas.
- **Alternativas:** A) Un dataset público de rendimiento escolar (otro país, sin plazos ni asuetos). B) Un generador propio.
- **Decisión:** B. `src/ingesta/generador.py` crea 10 millones de entregas con semilla fija. El riesgo de entrega tardía sigue reglas explícitas (modalidad, plazo corto, asueto en medio, tipo de tarea, materia, propensión del estudiante) y se inyecta un 0,2 % de defectos (duplicados, notas fuera de rango, texto mal escrito) para que la limpieza tenga algo real que hacer.
- **Consecuencias:** los resultados del modelo muestran que el flujo funciona, no cómo se comportan los estudiantes salvadoreños; así se dice en el README. El volumen se puede regenerar sin subir datos pesados al repositorio.

## Decisión 005: Dask para limpiar y agregar, con tipos y particiones declarados

Fecha: 2026-10-28 · Estado: aceptada

- **Contexto:** los 10 M de filas en CSV ocupan más de 1 GB en disco y varias veces eso en memoria con Pandas, en una laptop de 8 GB.
- **Alternativas:** A) Pandas. B) Dask. C) PySpark para todo.
- **Decisión:** B para la limpieza y las agregaciones del panel. Se declaran los `dtype` (categorías para columnas repetitivas) y `blocksize="64MB"`, que deja ~1 partición por archivo. Las cuatro agregaciones se calculan con un solo `dask.compute` para leer los CSV una sola vez. La limpieza usa `map_partitions` porque el generador escribe a cada estudiante en una sola partición: los duplicados nunca cruzan particiones y se evita un *shuffle*.
- **Consecuencias:** ver la medición en `reports/tiempos_dask_vs_pandas.csv`.

## Decisión 006: PySpark para el historial del estudiante (ventanas y unión)

Fecha: 2026-10-28 · Estado: aceptada

- **Contexto:** el modelo necesita saber cómo le fue al estudiante antes: tasa de entregas tardías, número de tareas y nota promedio previas.
- **Alternativas:** A) `groupby().cumsum()` en Dask. B) Funciones de ventana de Spark.
- **Decisión:** B. Una ventana por estudiante ordenada por día con `rangeBetween(unboundedPreceding, -21)`: solo cuenta tareas asignadas al menos 21 días antes, cuyo resultado ya se conocía (el plazo más largo, 10 días hábiles, puede cruzar una semana de vacaciones). La tasa por docente se calcula en otra tabla, sin los estudiantes de la muestra de modelado, y se une con `broadcast`. La muestra (4 % de los estudiantes) se elige con un *hash* del número de estudiante, así que es determinista. Ver `docs/spark_vs_dask.md`.
- **Consecuencias:** en Windows, Spark 4 no puede leer ni escribir archivos locales sin `winutils.exe` y `hadoop.dll` (error `NativeIO$Windows.access0`). Para no depender de binarios de terceros, en Windows cada Parquet se lee con Pandas y pasa a Spark por Arrow, lote por lote; es equivalente porque cada estudiante está en un solo archivo, y además cabe en una laptop con poca RAM libre. En Linux o Docker se usa `spark.read.parquet` sobre la carpeta completa. La salida se escribe con Pandas. Dos ajustes de memoria (2026-11-02): PySpark 4.2 no convierte el texto de Pandas 3 (arreglos Arrow fragmentados) y caía a la vía lenta fila por fila, así que las columnas de texto se pasan como `object`; y tras cada lote se libera la referencia y se fuerza la recolección de basura, porque los lotes creados desde Pandas llenaban el *heap* del *driver*. Resultado: 10 M de filas en 6 min 40 s con 1,5 GB de *driver*.

## Decisión 007: validación por estudiante y F1 de la clase «tardía»

Fecha: 2026-10-28 · Estado: aceptada

- **Contexto:** un estudiante tiene unas 250 tareas; si sus tareas quedan repartidas entre entrenamiento y prueba, el modelo «reconoce» al estudiante y las métricas salen infladas.
- **Alternativas:** A) División aleatoria por fila. B) División por estudiante.
- **Decisión:** B: `GroupShuffleSplit` para la prueba y `StratifiedGroupKFold` en la búsqueda de hiperparámetros. Se reporta F1, precisión y exhaustividad de la clase «tardía», AUC ROC y AUC PR; la exactitud sola engaña con clases desbalanceadas. La calificación de la propia tarea se excluye: solo existe después de la entrega.
- **Consecuencias:** métricas más bajas pero honestas; el umbral de 0,5 con pesos balanceados prioriza la exhaustividad (avisar de más es preferible a no avisar).

## Decisión 008: MongoDB con validación Pydantic e índices compuestos

Fecha: 2026-10-28 · Estado: aceptada

- **Contexto:** la consulta principal de la PWA es «tareas de este número de estudiante, por fecha límite».
- **Decisión:** cada documento pasa por `TareaDocumento` (Pydantic, `extra="forbid"`) antes de `insert_one` o `insert_many`. Índices: `id_entrega` único, `(numero_estudiante, fecha_limite)` y `(estado, fecha_limite)`. El historial de cambios vive dentro del documento (`seguimiento`), que es justo el caso semiestructurado.
- **Consecuencias:** un documento sucio nunca llega a la base; la mejora del índice se mide con `explain` (`reports/mongo_explain.csv`).

## Decisión 009: S3 con prefijo propio y moto en las pruebas

Fecha: 2026-10-28 · Estado: aceptada

- **Contexto:** el equipo ya tiene el bucket `amzn-s3-practica-nosql` de la Práctica NoSQL.
- **Decisión:** ATE usa ese bucket bajo el prefijo `ate/` (`S3_PREFIX`), con credenciales solo por variables de entorno. Las pruebas usan `moto` y un cliente simulado para el error 403; nunca tocan la red. `S3_ENDPOINT_URL` permite usar MinIO en local con el mismo código. Equivalencia en Google Cloud: Cloud Storage con `google-cloud-storage` (bucket ↔ bucket, objeto ↔ blob, IAM ↔ IAM).
- **Consecuencias:** se comparte un bucket sin mezclar archivos; borrar ATE es borrar un prefijo.

## Decisión 010: MLP en Keras como modelo de aprendizaje profundo

Fecha: 2026-10-28 · Estado: aceptada

- **Contexto:** los datos son tabulares; no hay imágenes, texto ni secuencias largas que justifiquen una CNN o una LSTM.
- **Decisión:** MLP de dos capas ocultas (64 y 32) con dropout 0,3, `EarlyStopping` sobre la pérdida de validación y pesos de clase balanceados, con el mismo preprocesador de los modelos clásicos.
- **Consecuencias:** la API sirve el mejor modelo de scikit-learn para no meter TensorFlow en la imagen Docker; el MLP queda en `models/` y en la comparación.

## Decisión 011: Gitflow para el trabajo en equipo

Fecha: 2026-11-02 · Estado: aceptada

- **Contexto:** hasta el Hito II el repositorio tuvo un solo autor y las ramas se integraban directo en `main`; la guía exige ramas, *pull requests* y un reparto equilibrado de commits.
- **Alternativas:** A) GitHub Flow (solo `main` y ramas cortas). B) Gitflow (`main`, `develop`, `feature/*`, `release/*`, `hotfix/*`).
- **Decisión:** B. `develop` concentra el trabajo de los tres integrantes y `main` solo recibe versiones etiquetadas, que es lo que se evalúa (`v1.0.0`).
- **Consecuencias:** cada integrante trabaja en su rama `feature/HU-xx` y abre un *pull request* hacia `develop`; la versión final sale por una rama `release/v1.0.0`.
