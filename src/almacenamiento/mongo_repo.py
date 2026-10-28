"""Repositorio de tareas en MongoDB (Atlas, contenedor local o mongomock en pruebas).

Uso::

    python -m src.almacenamiento.mongo_repo --cargar 50000   # carga una muestra y mide el índice
"""
from __future__ import annotations

import argparse
import os
import time
from datetime import datetime
from typing import Any, Iterable, Optional

from pydantic import ValidationError
from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.errors import BulkWriteError

from src.almacenamiento.esquemas import Estado, TareaDocumento


class DocumentoInvalidoError(ValueError):
    """El documento no cumple el esquema :class:`TareaDocumento`."""


class RepositorioTareas:
    """Acceso a la colección ``tareas`` con validación previa y cierre explícito.

    Se puede usar como gestor de contexto para garantizar que la conexión se cierre::

        with RepositorioTareas.desde_entorno() as repo:
            repo.buscar_por_estudiante("E0000001")

    Args:
        cliente: Un ``MongoClient`` (o ``mongomock.MongoClient`` en pruebas).
        base: Nombre de la base de datos.
        coleccion: Nombre de la colección.
    """

    def __init__(self, cliente: MongoClient, base: str = "ate", coleccion: str = "tareas") -> None:
        self._cliente = cliente
        self._coleccion: Collection = cliente[base][coleccion]
        self._abierto = True

    @classmethod
    def desde_entorno(cls) -> "RepositorioTareas":
        """Crea el repositorio con ``MONGODB_URI`` y ``MONGODB_DB`` del entorno.

        Raises:
            RuntimeError: Si ``MONGODB_URI`` no está definida.
        """
        uri = os.environ.get("MONGODB_URI")
        if not uri:
            raise RuntimeError("Defina MONGODB_URI (ver .env.example)")
        return cls(MongoClient(uri, serverSelectionTimeoutMS=10000), os.environ.get("MONGODB_DB", "ate"))

    def __enter__(self) -> "RepositorioTareas":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.cerrar()

    def __repr__(self) -> str:
        estado = "abierto" if self._abierto else "cerrado"
        return f"RepositorioTareas(coleccion={self._coleccion.full_name!r}, {estado})"

    # ------------------------------------------------------------------ escritura
    @staticmethod
    def validar(documento: dict) -> dict:
        """Valida un documento contra el esquema y lo devuelve normalizado.

        Raises:
            DocumentoInvalidoError: Si el documento no cumple el esquema.
        """
        try:
            return TareaDocumento(**documento).model_dump()
        except ValidationError as error:
            raise DocumentoInvalidoError(str(error)) from error

    def crear_indices(self) -> list[str]:
        """Crea los índices que usan las consultas de la API.

        Returns:
            Nombres de los índices creados.
        """
        return [
            self._coleccion.create_index("id_entrega", unique=True),
            self._coleccion.create_index([("numero_estudiante", ASCENDING), ("fecha_limite", ASCENDING)]),
            self._coleccion.create_index([("estado", ASCENDING), ("fecha_limite", ASCENDING)]),
        ]

    def insertar(self, documento: dict) -> str:
        """Valida e inserta una tarea con ``insert_one``.

        Returns:
            El ``id_entrega`` insertado.
        """
        limpio = self.validar(documento)
        self._coleccion.insert_one(limpio)
        return limpio["id_entrega"]

    def insertar_lote(self, documentos: Iterable[dict]) -> int:
        """Valida todos los documentos y los inserta con ``insert_many``.

        Si uno solo es inválido no se inserta ninguno.

        Returns:
            Número de documentos insertados.
        """
        limpios = [self.validar(d) for d in documentos]
        if not limpios:
            return 0
        try:
            return len(self._coleccion.insert_many(limpios, ordered=False).inserted_ids)
        except BulkWriteError as error:
            return error.details.get("nInserted", 0)

    def registrar_entrega(self, id_entrega: str, fecha: datetime, estado: Estado = Estado.ENTREGADA) -> bool:
        """Marca una tarea como entregada y añade el evento al seguimiento.

        Returns:
            True si se encontró y actualizó la tarea.
        """
        estado = Estado(estado).value
        resultado = self._coleccion.update_one(
            {"id_entrega": id_entrega},
            {"$set": {"estado": estado, "fecha_entrega": fecha},
             "$push": {"seguimiento": {"fecha": fecha, "estado": estado, "nota": None}}})
        return resultado.modified_count == 1

    # ------------------------------------------------------------------ consultas
    def buscar_por_estudiante(self, numero_estudiante: str) -> dict[str, list[dict]]:
        """Tareas de un estudiante separadas en pendientes y cerradas, por fecha límite.

        Returns:
            ``{"pendientes": [...], "entregadas": [...]}`` sin el ``_id`` de MongoDB.
        """
        docs = list(self._coleccion.find({"numero_estudiante": numero_estudiante}, {"_id": 0})
                    .sort("fecha_limite", ASCENDING))
        return {"pendientes": [d for d in docs if d["estado"] == Estado.PENDIENTE.value],
                "entregadas": [d for d in docs if d["estado"] != Estado.PENDIENTE.value]}

    def vencen_entre(self, desde: datetime, hasta: datetime, estado: Optional[str] = None) -> list[dict]:
        """Tareas cuya fecha límite está estrictamente entre ``desde`` y ``hasta`` ($gt / $lt).

        Args:
            desde: Límite inferior (excluido).
            hasta: Límite superior (excluido).
            estado: Si se indica, filtra por ese estado.
        """
        filtro: dict[str, Any] = {"fecha_limite": {"$gt": desde, "$lt": hasta}}
        if estado:
            filtro["estado"] = estado
        return list(self._coleccion.find(filtro, {"_id": 0}).sort("fecha_limite", ASCENDING))

    def riesgo_alto(self, umbral: float = 0.5) -> list[dict]:
        """Tareas pendientes con riesgo estimado mayor que ``umbral``."""
        return list(self._coleccion.find({"estado": "pendiente", "riesgo_tardia": {"$gt": umbral}},
                                         {"_id": 0}).sort("riesgo_tardia", -1))

    def contar(self, filtro: Optional[dict] = None) -> int:
        """Número de documentos que cumplen ``filtro``."""
        return self._coleccion.count_documents(filtro or {})

    def explicar(self, filtro: dict) -> dict:
        """Resumen de ``explain`` de una consulta: plan elegido y documentos examinados."""
        plan = self._coleccion.find(filtro).explain()
        stats = plan.get("executionStats", {})
        ganador = plan.get("queryPlanner", {}).get("winningPlan", {})
        etapa = ganador.get("stage") or ganador.get("queryPlan", {}).get("stage")
        hijo = ganador.get("inputStage", {}).get("stage") or ganador.get("queryPlan", {}).get("inputStage", {}).get("stage")
        return {"etapa": etapa, "subetapa": hijo, "docs_examinados": stats.get("totalDocsExamined"),
                "devueltos": stats.get("nReturned"), "ms": stats.get("executionTimeMillis")}

    def borrar_todo(self) -> int:
        """Vacía la colección (solo para cargas de demostración)."""
        return self._coleccion.delete_many({}).deleted_count

    def cerrar(self) -> None:
        """Cierra la conexión con el servidor."""
        if self._abierto:
            self._cliente.close()
            self._abierto = False


def documento_desde_fila(fila: dict) -> dict:
    """Convierte una fila del dataset en un documento de :class:`TareaDocumento`."""
    entrega = fila.get("fecha_entrega")
    nota = fila.get("calificacion")
    doc = {k: fila[k] for k in ("id_entrega", "numero_estudiante", "centro", "grado", "seccion", "modalidad",
                                "materia", "tipo_tarea", "prioridad", "fecha_asignacion", "fecha_limite",
                                "estado")}
    doc["fecha_entrega"] = entrega if entrega == entrega and entrega not in ("", None) else None
    doc["calificacion"] = None if nota != nota or nota is None else float(nota)
    doc["seguimiento"] = [{"fecha": fila["fecha_asignacion"], "estado": "pendiente", "nota": "asignada"}]
    if doc["estado"] != "pendiente" and doc["fecha_entrega"] is not None:
        doc["seguimiento"].append({"fecha": doc["fecha_entrega"], "estado": doc["estado"], "nota": None})
    return doc


def main() -> None:
    """Carga una muestra del dataset limpio y compara la consulta con y sin índice."""
    import pandas as pd
    from dotenv import load_dotenv

    from src.ingesta.generador import ruta_datos

    p = argparse.ArgumentParser(description=main.__doc__)
    p.add_argument("--cargar", type=int, default=50_000)
    args = p.parse_args()
    load_dotenv()
    # Basta un archivo de la carpeta (≈500 000 filas); el plan gratuito de Atlas admite 512 MB.
    primero = sorted((ruta_datos() / "processed" / "entregas_limpias").glob("*.parquet"))[0]
    df = pd.read_parquet(primero).head(args.cargar)
    with RepositorioTareas.desde_entorno() as repo:
        repo.borrar_todo()
        repo._coleccion.drop_indexes()
        t = time.perf_counter()
        n = repo.insertar_lote(documento_desde_fila(f) for f in df.to_dict("records"))
        print(f"{repo}: {n} documentos en {time.perf_counter() - t:.1f} s")
        estudiante = df["numero_estudiante"].iloc[len(df) // 2]
        filtro = {"numero_estudiante": estudiante, "fecha_limite": {"$gt": datetime(2026, 9, 1)}}
        sin = repo.explicar(filtro)
        repo.crear_indices()
        con = repo.explicar(filtro)
        print("sin índice:", sin)
        print("con índice:", con)
        pd.DataFrame([{"caso": "sin_indice", **sin}, {"caso": "con_indice", **con}]).to_csv(
            "reports/mongo_explain.csv", index=False)


if __name__ == "__main__":
    main()
