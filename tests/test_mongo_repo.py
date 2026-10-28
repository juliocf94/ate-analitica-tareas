"""Pruebas del repositorio MongoDB con mongomock: nunca tocan la red (HU-08)."""
from datetime import datetime

import mongomock
import pytest

from src.almacenamiento.mongo_repo import DocumentoInvalidoError, RepositorioTareas


@pytest.fixture
def repo():
    r = RepositorioTareas(mongomock.MongoClient(), base="ate_test")
    yield r
    r.cerrar()


def test_insertar_y_consultar_por_estudiante(repo, documento):
    repo.insertar(documento)
    repo.insertar({**documento, "id_entrega": "T000-0000002", "estado": "entregada",
                   "fecha_entrega": datetime(2026, 10, 22), "calificacion": 9.0})
    resultado = repo.buscar_por_estudiante("E0000001")
    assert len(resultado["pendientes"]) == 1 and len(resultado["entregadas"]) == 1
    assert "_id" not in resultado["pendientes"][0]


def test_documento_invalido_no_se_inserta(repo, documento):
    with pytest.raises(DocumentoInvalidoError):
        repo.insertar({**documento, "calificacion": "nueve"})
    with pytest.raises(DocumentoInvalidoError):
        repo.insertar({**documento, "fecha_limite": datetime(2026, 10, 1)})   # antes de la asignación
    with pytest.raises(DocumentoInvalidoError):
        repo.insertar_lote([documento, {**documento, "numero_estudiante": "Juan Pérez"}])
    assert repo.contar() == 0


def test_consulta_con_gt_y_lt(repo, documento):
    repo.insertar_lote([{**documento, "id_entrega": f"TX-{i}", "fecha_limite": datetime(2026, 10, 21 + i)}
                        for i in range(5)])
    vencen = repo.vencen_entre(datetime(2026, 10, 22), datetime(2026, 10, 25))
    assert [d["id_entrega"] for d in vencen] == ["TX-2", "TX-3"]


def test_indices_y_entrega_registrada(repo, documento):
    nombres = repo.crear_indices()
    assert "id_entrega_1" in nombres
    repo.insertar(documento)
    assert repo.registrar_entrega("T000-0000001", datetime(2026, 10, 22))
    doc = repo.buscar_por_estudiante("E0000001")["entregadas"][0]
    assert doc["estado"] == "entregada" and doc["seguimiento"][-1]["estado"] == "entregada"


def test_cierre_de_conexion(documento):
    cliente = mongomock.MongoClient()
    with RepositorioTareas(cliente) as repo:
        repo.insertar(documento)
    assert "cerrado" in repr(repo)
