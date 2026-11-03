# ATE — Analítica de Tareas Educativas

> Tareas claras para las familias y alertas tempranas de retraso para la escuela.

Proyecto Integrador del Módulo 4 (Big Data y MLOps), Bootcamp Python para Ciencia de Datos.
Estado: Hito II, cierre del Sprint 1 (datos, almacenamiento y modelos). La API, Docker y la PWA
llegan en el Sprint 2.

## 1. Problema y contexto

En muchas escuelas las tareas se registran a mano o se dispersan entre cuadernos, mensajes y chats.
Las familias se enteran de los retrasos cuando ya afectan la nota, y la coordinación no ve a tiempo
dónde se acumulan. ATE centraliza las tareas, deja consultarlas solo con el número de estudiante y
estima qué tareas tienen riesgo de entregarse tarde, con plazos calculados según el calendario
escolar salvadoreño (asuetos, vacaciones y modalidades nocturna, de fin de semana y a distancia).

## 2. Solución y resultados clave

| Pieza | Resultado |
| --- | --- |
| Datos | 10 millones de entregas sintéticas reproducibles (`src/ingesta/generador.py`) |
| Dask | Limpia y agrega los 10 M de filas en 45 s; Pandas no cabe en la RAM libre desde 2,5 M |
| PySpark | Historial previo de cada estudiante con ventanas y un *join* con *broadcast* |
| MongoDB | 50 000 tareas en Atlas con validación Pydantic y 3 índices; la consulta principal pasa de 390 ms (`COLLSCAN`, 50 000 documentos) a 1 ms (`IXSCAN`, 79 documentos) |
| S3 | Subida y descarga con `boto3`, errores 403 y 404 controlados |
| Modelos | F1 de 0,48 frente a 0,25 del baseline; AUC ROC 0,71 |
| Finanzas | ROI de 4,6 veces a 24 meses y recuperación en el mes 14 (escenario base) |

Comparación en el conjunto de prueba (71 765 tareas de estudiantes que el modelo nunca vio; clase positiva: entrega tardía):

| Modelo | F1 | Precisión | Exhaustividad | AUC ROC | AUC PR |
| --- | --- | --- | --- | --- | --- |
| MLP (Keras) | 0,483 | 0,395 | 0,621 | 0,709 | 0,463 |
| Regresión logística (**la que sirve la API**) | 0,481 | 0,403 | 0,596 | 0,707 | 0,458 |
| Random Forest | 0,480 | 0,406 | 0,586 | 0,709 | 0,462 |
| SVM lineal calibrada | 0,283 | 0,593 | 0,186 | 0,707 | 0,458 |
| Baseline estratificado | 0,255 | 0,251 | 0,259 | 0,498 | 0,253 |

Los tres mejores empatan: la señal es casi aditiva y un modelo lineal ya la captura. Se elige la
regresión logística porque es interpretable, pesa 7 KB y no necesita TensorFlow en la imagen Docker.
Curvas del MLP en `reports/figures/curvas_mlp.png` y análisis de errores por subgrupo en
`reports/analisis_errores.csv` (el punto débil es el estudiante sin historial: AUC 0,56).

## 3. Arquitectura

```
CSV/Parquet sintéticos ──► Dask (limpieza y agregación) ──► Parquet limpio ──► PySpark (historial)
                                       │                                              │
                                       ▼                                              ▼
                              MongoDB (tareas y seguimiento)                 Modelos ML y MLP
                                       │                                              │
                                       └──────────► API FastAPI (Sprint 2) ◄──────────┘
                                                        │            S3: datos y artefactos
                                                        ▼
                                                   PWA React
```

Cada componente está justificado en [`docs/decisiones.md`](docs/decisiones.md), y la comparación
Dask frente a PySpark está en [`docs/spark_vs_dask.md`](docs/spark_vs_dask.md).

## 4. Datos

- **Fuente:** generador propio y determinista (`semilla=42`). No hay ningún dato personal real: el
  número de estudiante es un código sintético. Licencia MIT, igual que el código.
- **Volumen:** 10 millones de entregas de 40 000 estudiantes en 60 centros; se inyecta un 0,2 % de
  defectos (duplicados, notas fuera de rango, texto mal escrito) para probar la limpieza.
- **Muestra versionada:** `data/muestra/entregas_muestra.csv` (5 000 filas). Los datos completos no
  se suben; se regeneran con el comando de la sección 5.

| Variable | Descripción |
| --- | --- |
| `id_entrega`, `numero_estudiante`, `centro`, `docente` | Códigos sintéticos |
| `distrito`, `grado`, `seccion`, `modalidad`, `turno` | Datos de la sección |
| `materia`, `tipo_tarea`, `prioridad` | Datos de la tarea |
| `fecha_asignacion`, `fecha_limite`, `dias_plazo_habiles`, `cruza_asueto` | Plazo según el calendario 2026 |
| `fecha_entrega`, `estado`, `calificacion` | Resultado (`pendiente`, `entregada` o `tardia`) |
| `entrega_tardia` | Variable objetivo: 1 si se entregó tarde o no se entregó |

**Sesgos:** los patrones los definen las reglas del generador; los resultados muestran que el flujo
funciona, no cómo se comportan los estudiantes salvadoreños.

## 5. Instalación y ejecución

Requiere Python 3.12 y, para PySpark, un JDK 17 o 21.

```bash
git clone https://github.com/juliocf94/ate-analitica-tareas.git && cd ate-analitica-tareas
python -m venv .venv && .venv\Scripts\activate      # en Linux o macOS: source .venv/bin/activate
pip install -r requirements.txt
pytest                                              # pruebas, sin red

# Pipeline completo (los datos se guardan en ATE_DATA_DIR o en data/)
python -m src.ingesta.generador --filas 10000000 --particiones 20
python -m src.ingesta.dask_pipeline                 # limpieza y agregaciones
python -m src.ingesta.dask_pipeline --benchmark     # Dask frente a Pandas
python -m src.ingesta.spark_etl --fraccion 0.04     # historial con PySpark
python -m src.modelos.entrenar                      # modelos y reportes
python -m src.utils.finanzas                        # flujo de caja y ROI
```

MongoDB y S3 se configuran con variables de entorno: copiar `.env.example` como `.env` y rellenar.
Con `MONGODB_URI=mongodb://localhost:27017` y `S3_ENDPOINT_URL=http://localhost:9000` (MinIO) todo
corre en local y sin costo.

```bash
python -m src.almacenamiento.mongo_repo --cargar 50000   # carga y compara con y sin índice
python -m src.almacenamiento.almacen_s3 subir models/modelo_ate.joblib modelos/modelo_ate.joblib
```

Salida de `pytest`:

```
tests/test_almacen_s3.py    ....
tests/test_calendario.py    .....
tests/test_datos.py         ....
tests/test_finanzas.py      ..
tests/test_modelos.py       .....
tests/test_mongo_repo.py    .....
tests/test_spark.py         .
26 passed in 55.36s
```

## 6. Uso de la API

Sprint 2: `GET /health`, `POST /v1/predict` y Swagger en `/docs`, dentro de un contenedor Docker.

## 7. Decisiones y trazabilidad

| Requisito de la guía | Archivo |
| --- | --- |
| Dask con `dtype`, particiones y `.compute()` | `src/ingesta/dask_pipeline.py`, `reports/tiempos_dask_vs_pandas.csv` |
| PySpark: ventanas, *join*, transformaciones y acciones | `src/ingesta/spark_etl.py`, `docs/spark_vs_dask.md` |
| MongoDB con validación, índices y consultas | `src/almacenamiento/mongo_repo.py`, `tests/test_mongo_repo.py` |
| S3 simulado con manejo del error 403 | `src/almacenamiento/almacen_s3.py`, `tests/test_almacen_s3.py` |
| POO: clase base abstracta, herencia, Strategy | `src/ingesta/base.py`, `src/modelos/base.py` |
| Baseline, 3 modelos ML y un MLP | `src/modelos/`, `reports/metricas_modelos.csv`, `reports/figures/curvas_mlp.png` |
| Pruebas pytest con mocks | `tests/` |
| Evaluación financiera (Hito II) | `src/utils/finanzas.py`, `reports/escenarios_financieros.csv` |
| Registro de decisiones | [`docs/decisiones.md`](docs/decisiones.md) |
| Bitácora del Hito II y capturas de S3 y Atlas | `docs/Hito_II_ATE.pdf`, `docs/capturas/` |

## 8. Limitaciones, riesgos éticos y trabajo futuro

- Los datos son sintéticos: las métricas no se trasladan a una escuela real sin reentrenar.
- El indicador de riesgo es una alerta temprana, nunca una calificación ni una sanción.
- No se guardan nombres, fotos ni datos de contacto de menores (Decreto 144 y Ley Crecer Juntos).
- En Windows, Spark lee los Parquet a través de Pandas porque no hay `winutils.exe`; en Linux o
  Docker usa `spark.read.parquet`.
- Trabajo futuro: API y contenedor, PWA, recordatorios y prueba de usabilidad con familias.

## 9. Flujo de trabajo con Git (Gitflow)

| Rama | Uso |
| --- | --- |
| `main` | Solo versiones estables y etiquetadas (`v0.2.0` = Hito II, `v1.0.0` = entrega final) |
| `develop` | Rama de integración: aquí convergen todos los cambios antes de pasar a `main` |
| `feature/HU-xx-nombre` | Una rama por historia de usuario; sale de `develop` y vuelve por *pull request* revisado |
| `release/vX.Y.Z` | Preparación de una versión: solo correcciones, luego se fusiona en `main` y `develop` |
| `hotfix/nombre` | Corrección urgente sobre `main` |

Ramas personales para el Sprint 2 (cada una sale de `develop` y vuelve por *pull request*):

| Rama | Responsable | Trabajo |
| --- | --- | --- |
| `feature/mauricio-api-docker` | Mauricio Castro | API FastAPI (`/health`, `/v1/predict`), Dockerfile y PWA |
| `feature/claudia-readme-calidad` | Claudia Carballo | README final, pruebas de la API y revisión de *pull requests* |

Para empezar a trabajar (ejemplo con la rama de Mauricio):

```bash
git clone https://github.com/juliocf94/ate-analitica-tareas.git && cd ate-analitica-tareas
git checkout feature/mauricio-api-docker
git config user.name "Nombre Apellido" && git config user.email "correo@ejemplo.com"
# ... cambios y commits ...
git push                                        # y abrir un pull request hacia develop
```

Antes de cada sesión conviene traer lo último de `develop`: `git pull origin develop`.

## 10. Equipo

| Integrante | Rol |
| --- | --- |
| Julio César Flores Fuentes | Project Manager · Ingeniería de datos |
| Mauricio Enrique Castro Flores | Product Owner · Producto y MLOps |
| Claudia Patricia Carballo Larios | Scrum Master · Calidad y documentación |

## 11. Licencia

[MIT](LICENSE).

## 12. Uso de inteligencia artificial

El equipo usó Claude (Anthropic, modelo Opus 5.5) como asistente para escribir y revisar código y
pruebas, depurar PySpark y redactar la documentación. Las decisiones y la revisión de resultados son
del equipo, y cada integrante puede explicar y modificar cualquier parte del proyecto.
