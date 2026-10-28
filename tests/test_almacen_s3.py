"""Pruebas del almacén S3 con moto (simulación en memoria, sin red) (HU-09)."""
from unittest.mock import MagicMock

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from src.almacenamiento.almacen_s3 import AccesoDenegadoError, AlmacenS3, ObjetoNoEncontradoError


@pytest.fixture
def almacen(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "prueba")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "prueba")
    monkeypatch.delenv("S3_ENDPOINT_URL", raising=False)
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="ate-pruebas")
        yield AlmacenS3("ate-pruebas", boto3.client("s3", region_name="us-east-1"), prefijo="ate/")


def test_subir_y_descargar(almacen, tmp_path):
    origen = tmp_path / "modelo.joblib"
    origen.write_bytes(b"contenido del modelo")
    assert almacen.subir(origen, "modelos/modelo.joblib") == "s3://ate-pruebas/ate/modelos/modelo.joblib"
    assert almacen.listar("modelos/") == ["modelos/modelo.joblib"]
    destino = almacen.descargar("modelos/modelo.joblib", tmp_path / "copia" / "modelo.joblib")
    assert destino.read_bytes() == b"contenido del modelo"


def test_clave_inexistente_y_archivo_local_inexistente(almacen, tmp_path):
    assert not almacen.existe("no/existe.csv")
    with pytest.raises(ObjetoNoEncontradoError):
        almacen.descargar("no/existe.csv", tmp_path / "x.csv")
    with pytest.raises(FileNotFoundError):
        almacen.subir(tmp_path / "falta.csv", "datos/falta.csv")


def test_error_403_se_traduce(tmp_path):
    cliente = MagicMock()
    cliente.download_file.side_effect = ClientError(
        {"Error": {"Code": "403", "Message": "Forbidden"}, "ResponseMetadata": {"HTTPStatusCode": 403}},
        "HeadObject")
    with pytest.raises(AccesoDenegadoError, match="Acceso denegado"):
        AlmacenS3("bucket-ajeno", cliente).descargar("datos.csv", tmp_path / "datos.csv")


def test_credenciales_solo_por_entorno(monkeypatch):
    monkeypatch.delenv("S3_BUCKET", raising=False)
    with pytest.raises(Exception, match="S3_BUCKET"):
        AlmacenS3.desde_entorno()
