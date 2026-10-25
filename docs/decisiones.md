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
