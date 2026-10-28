"""Almacén de objetos compatible con S3 (AWS, MinIO local o moto en pruebas).

Las credenciales se leen solo de variables de entorno (``AWS_ACCESS_KEY_ID``,
``AWS_SECRET_ACCESS_KEY``); ``S3_ENDPOINT_URL`` apunta a MinIO si se define.

Uso::

    python -m src.almacenamiento.almacen_s3 subir models/modelo_ate.joblib modelos/modelo_ate.joblib
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Optional

import boto3
from boto3.exceptions import S3UploadFailedError
from botocore.exceptions import ClientError, NoCredentialsError


class AlmacenError(RuntimeError):
    """Error base del almacén de objetos."""


class AccesoDenegadoError(AlmacenError):
    """El servidor respondió 403: credenciales sin permiso sobre el bucket."""


class ObjetoNoEncontradoError(AlmacenError):
    """La clave o el bucket no existen (404)."""


class AlmacenS3:
    """Sube y descarga archivos de un bucket S3 con manejo de errores explícito.

    Args:
        bucket: Nombre del bucket.
        cliente: Cliente de boto3; si es None se crea con las variables de entorno.
        prefijo: Carpeta dentro del bucket (p. ej. ``ate/``); se antepone a cada clave
            para compartir un bucket con otros proyectos sin mezclar archivos.

    Example:
        >>> almacen = AlmacenS3.desde_entorno()            # doctest: +SKIP
        >>> almacen.subir("models/modelo_ate.joblib", "modelos/modelo_ate.joblib")  # doctest: +SKIP
    """

    def __init__(self, bucket: str, cliente=None, prefijo: str = "") -> None:
        self._bucket = bucket
        self._prefijo = prefijo.strip("/") + "/" if prefijo.strip("/") else ""
        self._s3 = cliente or boto3.client(
            "s3", region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
            endpoint_url=os.environ.get("S3_ENDPOINT_URL") or None)

    @classmethod
    def desde_entorno(cls) -> "AlmacenS3":
        """Crea el almacén con ``S3_BUCKET`` y ``S3_PREFIX`` (opcional) del entorno.

        Raises:
            AlmacenError: Si ``S3_BUCKET`` no está definida.
        """
        bucket = os.environ.get("S3_BUCKET")
        if not bucket:
            raise AlmacenError("Defina S3_BUCKET (ver .env.example)")
        return cls(bucket, prefijo=os.environ.get("S3_PREFIX", ""))

    def __repr__(self) -> str:
        return f"AlmacenS3(bucket={self._bucket!r}, prefijo={self._prefijo!r})"

    def _clave(self, clave: str) -> str:
        return self._prefijo + clave.lstrip("/")

    @staticmethod
    def _traducir(error: ClientError, clave: str) -> AlmacenError:
        codigo = str(error.response.get("Error", {}).get("Code", ""))
        estado = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if codigo in ("403", "AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch") or estado == 403:
            return AccesoDenegadoError(f"Acceso denegado a {clave!r}: revise las credenciales y la política del bucket")
        if codigo in ("404", "NoSuchKey", "NoSuchBucket", "NotFound") or estado == 404:
            return ObjetoNoEncontradoError(f"No existe {clave!r}")
        return AlmacenError(f"Error de S3 ({codigo}) con {clave!r}")

    def subir(self, ruta_local: str | Path, clave: str) -> str:
        """Sube un archivo con ``upload_file``.

        Args:
            ruta_local: Archivo a subir.
            clave: Clave de destino en el bucket.

        Returns:
            La URI ``s3://bucket/clave``.

        Raises:
            FileNotFoundError: Si el archivo local no existe.
            AccesoDenegadoError: Si el servidor responde 403.
            AlmacenError: Ante cualquier otro error del servicio o de credenciales.
        """
        ruta_local = Path(ruta_local)
        if not ruta_local.is_file():
            raise FileNotFoundError(ruta_local)
        try:
            self._s3.upload_file(str(ruta_local), self._bucket, self._clave(clave))
        except ClientError as error:
            raise self._traducir(error, clave) from error
        except NoCredentialsError as error:
            raise AlmacenError("No hay credenciales de AWS en el entorno") from error
        except S3UploadFailedError as error:
            if "403" in str(error) or "AccessDenied" in str(error):
                raise AccesoDenegadoError(f"Acceso denegado a {clave!r}") from error
            raise AlmacenError(str(error)) from error
        return f"s3://{self._bucket}/{self._clave(clave)}"

    def descargar(self, clave: str, ruta_local: str | Path) -> Path:
        """Descarga un objeto con ``download_file``.

        Raises:
            ObjetoNoEncontradoError: Si la clave no existe.
            AccesoDenegadoError: Si el servidor responde 403.
        """
        ruta_local = Path(ruta_local)
        ruta_local.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._s3.download_file(self._bucket, self._clave(clave), str(ruta_local))
        except ClientError as error:
            raise self._traducir(error, clave) from error
        except NoCredentialsError as error:
            raise AlmacenError("No hay credenciales de AWS en el entorno") from error
        return ruta_local

    def listar(self, prefijo: str = "") -> list[str]:
        """Claves (sin el prefijo del almacén) que empiezan con ``prefijo``."""
        try:
            pagina = self._s3.list_objects_v2(Bucket=self._bucket, Prefix=self._clave(prefijo))
        except ClientError as error:
            raise self._traducir(error, prefijo) from error
        return [o["Key"][len(self._prefijo):] for o in pagina.get("Contents", [])]

    def existe(self, clave: str) -> bool:
        """True si la clave existe en el bucket."""
        try:
            self._s3.head_object(Bucket=self._bucket, Key=self._clave(clave))
            return True
        except ClientError as error:
            if isinstance(self._traducir(error, clave), ObjetoNoEncontradoError):
                return False
            raise self._traducir(error, clave) from error


def main(argv: Optional[list[str]] = None) -> None:
    """Línea de comandos: ``subir``, ``descargar`` o ``listar``."""
    from dotenv import load_dotenv

    load_dotenv()
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("accion", choices=["subir", "descargar", "listar"])
    p.add_argument("args", nargs="*")
    a = p.parse_args(argv)
    almacen = AlmacenS3.desde_entorno()
    if a.accion == "subir":
        print(almacen.subir(a.args[0], a.args[1]))
    elif a.accion == "descargar":
        print(almacen.descargar(a.args[0], a.args[1]))
    else:
        print("\n".join(almacen.listar(a.args[0] if a.args else "")))


if __name__ == "__main__":
    main()
