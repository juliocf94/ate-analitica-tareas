"""Limpieza y agregación de las entregas con Dask, y su comparación con Pandas.

Uso::

    python -m src.ingesta.dask_pipeline            # limpia, agrega y guarda Parquet
    python -m src.ingesta.dask_pipeline --benchmark  # mide Dask frente a Pandas
"""
from __future__ import annotations

import argparse
import gc
import os
import time
from pathlib import Path

import dask
import dask.dataframe as dd
import pandas as pd
import psutil

from src.ingesta.base import EtapaPipeline
from src.ingesta.generador import MATERIAS, ruta_datos

RAIZ = Path(__file__).resolve().parents[2]

#: Tipos declarados de forma explícita: Dask infiere con la primera partición y
#: fallaría más adelante si una columna cambia de tipo (p. ej., fecha_entrega vacía).
DTYPES = {
    "id_entrega": "string", "numero_estudiante": "string", "centro": "category",
    "distrito": "category", "grado": "category", "seccion": "category", "modalidad": "category",
    "turno": "category", "materia": "string", "docente": "string", "tipo_tarea": "category",
    "prioridad": "category", "fecha_asignacion": "string", "fecha_limite": "string",
    "dias_plazo_habiles": "int16", "cruza_asueto": "bool", "fecha_entrega": "string",
    "estado": "category", "calificacion": "float32", "entrega_tardia": "float32",
}

#: Tamaño de bloque al leer CSV. Cada archivo del generador pesa unos 70 MB, así
#: que queda ~1 partición por archivo: suficiente paralelismo para 8 hilos sin
#: que la gestión de cientos de particiones pequeñas domine el tiempo.
BLOCKSIZE = "64MB"

_CANONICA = {m.upper(): m for m in MATERIAS}


def limpiar_particion(df: pd.DataFrame) -> pd.DataFrame:
    """Limpia una partición: duplicados, texto inconsistente y valores fuera de rango.

    Se aplica con ``map_partitions``: el generador escribe cada estudiante en una
    sola partición, así que los duplicados nunca cruzan particiones y no hace
    falta un *shuffle* global.

    Args:
        df: Partición cruda con las columnas de :data:`DTYPES`.

    Returns:
        Partición limpia, con fechas como ``datetime64``.
    """
    df = df.drop_duplicates(subset="id_entrega")
    materia = df["materia"].str.strip().str.upper().map(_CANONICA)
    df = df.assign(
        materia=materia.astype("string"),
        calificacion=df["calificacion"].where(df["calificacion"].between(0, 10)),
        fecha_asignacion=pd.to_datetime(df["fecha_asignacion"]),
        fecha_limite=pd.to_datetime(df["fecha_limite"]),
        fecha_entrega=pd.to_datetime(df["fecha_entrega"].replace("", None)),
    )
    return df


def limpiar(ddf: dd.DataFrame) -> dd.DataFrame:
    """Aplica :func:`limpiar_particion` a cada partición de un DataFrame de Dask.

    El ``meta`` se calcula con la partición vacía de muestra: así Dask conoce
    los tipos de salida sin tener que adivinarlos con datos ficticios.
    """
    return ddf.map_partitions(limpiar_particion, meta=limpiar_particion(ddf._meta))


def agregar(df) -> dict:
    """Define las agregaciones del panel de coordinación (sin ejecutarlas).

    Args:
        df: DataFrame limpio (Pandas o Dask).

    Returns:
        Diccionario nombre -> resultado (perezoso si ``df`` es de Dask).
    """
    cerradas = df[df["estado"] != "pendiente"]
    return {
        "tardia_por_grado_materia": cerradas.groupby(["grado", "materia"], observed=True)
        ["entrega_tardia"].agg(["mean", "count"]),
        "tardia_por_modalidad": cerradas.groupby("modalidad", observed=True)["entrega_tardia"].agg(["mean", "count"]),
        "tardia_por_asueto": cerradas.groupby("cruza_asueto")["entrega_tardia"].mean(),
        "pendientes_por_centro": df[df["estado"] == "pendiente"].groupby("centro", observed=True).size(),
    }


class LimpiezaDask(EtapaPipeline):
    """Lee las particiones CSV con Dask, las limpia, agrega y guarda en Parquet.

    Args:
        origen: Carpeta con ``entregas_*.csv``.
        destino: Carpeta ``data/processed``.
    """

    def __init__(self, origen: Path, destino: Path) -> None:
        super().__init__("limpieza_dask")
        self._origen = Path(origen)
        self._destino = Path(destino)

    def leer(self) -> dd.DataFrame:
        """Lectura perezosa y particionada con tipos explícitos."""
        return dd.read_csv(str(self._origen / "entregas_*.csv"), dtype=DTYPES, blocksize=BLOCKSIZE,
                           keep_default_na=False, na_values={"calificacion": [""], "entrega_tardia": [""]})

    def ejecutar(self, guardar: bool = True) -> dict:
        """Ejecuta limpieza y agregaciones en una sola pasada.

        Args:
            guardar: Si es True escribe ``entregas_limpias/`` y las agregaciones en Parquet.

        Returns:
            Diccionario con las agregaciones ya calculadas (objetos de Pandas).
        """
        crudo = self.leer()
        limpio = limpiar(crudo)
        perezosos = agregar(limpio)
        # Un solo dask.compute: el grafo comparte la lectura y la limpieza entre
        # todas las agregaciones, en lugar de leer los CSV una vez por cada una.
        resultados = dict(zip(perezosos, dask.compute(*perezosos.values())))
        if guardar:
            self._destino.mkdir(parents=True, exist_ok=True)
            limpio.to_parquet(str(self._destino / "entregas_limpias"), write_index=False, overwrite=True)
            for nombre, tabla in resultados.items():
                tabla.reset_index().to_parquet(self._destino / f"{nombre}.parquet", index=False)
        return resultados


def _pandas_completo(archivos: list[Path]) -> dict:
    df = pd.concat((pd.read_csv(a, dtype=DTYPES, keep_default_na=False,
                                na_values={"calificacion": [""], "entrega_tardia": [""]})
                    for a in archivos), ignore_index=True)
    return agregar(limpiar_particion(df))


class _MedidorPico:
    """Muestrea la memoria del proceso en un hilo aparte y guarda el máximo."""

    def __init__(self, intervalo: float = 0.05) -> None:
        import threading

        self._proceso = psutil.Process(os.getpid())
        self._intervalo = intervalo
        self._base = self._proceso.memory_info().rss
        self.pico = self._base
        self._parar = threading.Event()
        self._hilo = threading.Thread(target=self._muestrear, daemon=True)

    def _muestrear(self) -> None:
        while not self._parar.is_set():
            self.pico = max(self.pico, self._proceso.memory_info().rss)
            self._parar.wait(self._intervalo)

    def __enter__(self) -> "_MedidorPico":
        self._hilo.start()
        return self

    def __exit__(self, *exc) -> None:
        self._parar.set()
        self._hilo.join()

    @property
    def extra_gb(self) -> float:
        """Memoria máxima por encima del inicio, en GB."""
        return max(self.pico - self._base, 0) / 1e9


def benchmark(origen: Path, salida: Path, particiones: tuple[int, ...] = (1, 2, 5, 10, 20)) -> pd.DataFrame:
    """Mide tiempo y memoria de Pandas frente a Dask con volúmenes crecientes.

    Args:
        origen: Carpeta con los CSV crudos.
        salida: Carpeta ``reports/`` donde se guarda la tabla y la figura.
        particiones: Cantidades de archivos a procesar en cada medición.

    Returns:
        Tabla con filas, motor, segundos y memoria máxima observada.
    """
    archivos = sorted(Path(origen).glob("entregas_*.csv"))
    filas_por_archivo = sum(1 for _ in open(archivos[0], encoding="utf-8")) - 1
    registros = []
    for k in particiones:
        if k > len(archivos):
            continue
        sub = archivos[:k]
        for motor in ("pandas", "dask"):
            # Pandas carga todo en memoria: si la extrapolación de la primera
            # medición no cabe en el 70 % de la RAM libre, se registra y se omite.
            libre = psutil.virtual_memory().available / 1e9
            previo = [r for r in registros if r["motor"] == "pandas" and r["segundos"] is not None]
            if motor == "pandas" and previo and previo[0]["memoria_extra_gb"] * k / previo[0]["archivos"] > 0.7 * libre:
                registros.append({"archivos": k, "filas_aprox": k * filas_por_archivo, "motor": motor,
                                  "segundos": None, "memoria_extra_gb": None, "ram_libre_gb": round(libre, 1),
                                  "nota": f"omitido: memoria insuficiente ({libre:.1f} GB libres)"})
                print(registros[-1], flush=True)
                continue
            gc.collect()
            inicio = time.perf_counter()
            with _MedidorPico() as medidor:
                if motor == "pandas":
                    res = _pandas_completo(sub)
                else:
                    ddf = dd.read_csv([str(a) for a in sub], dtype=DTYPES, blocksize=BLOCKSIZE,
                                      keep_default_na=False,
                                      na_values={"calificacion": [""], "entrega_tardia": [""]})
                    perezosos = agregar(limpiar(ddf))
                    res = dict(zip(perezosos, dask.compute(*perezosos.values())))
            segundos = time.perf_counter() - inicio
            memoria = medidor.extra_gb
            registros.append({"archivos": k, "filas_aprox": k * filas_por_archivo, "motor": motor,
                              "segundos": round(segundos, 2), "memoria_extra_gb": round(memoria, 2),
                              "ram_libre_gb": round(libre, 1), "nota": ""})
            print(registros[-1], flush=True)
            del res
    tabla = pd.DataFrame(registros)
    salida.mkdir(parents=True, exist_ok=True)
    tabla.to_csv(salida / "tiempos_dask_vs_pandas.csv", index=False)
    _graficar(tabla, salida / "figures" / "tiempos_dask_vs_pandas.png")
    return tabla


def _graficar(tabla: pd.DataFrame, ruta: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ruta.parent.mkdir(parents=True, exist_ok=True)
    fig, ejes = plt.subplots(1, 2, figsize=(10, 4))
    for motor, color in (("pandas", "#9a3412"), ("dask", "#1f5fae")):
        t = tabla[(tabla["motor"] == motor) & tabla["segundos"].notna()]
        ejes[0].plot(t["filas_aprox"] / 1e6, t["segundos"], marker="o", color=color, label=motor)
        ejes[1].plot(t["filas_aprox"] / 1e6, t["memoria_extra_gb"], marker="o", color=color, label=motor)
    ejes[0].set(title="Tiempo de limpieza y agregación", xlabel="Millones de filas", ylabel="Segundos")
    ejes[1].set(title="Memoria máxima adicional del proceso", xlabel="Millones de filas", ylabel="GB")
    for eje in ejes:
        eje.grid(alpha=0.3)
        eje.legend()
    fig.tight_layout()
    fig.savefig(ruta, dpi=120)
    plt.close(fig)


def main() -> None:
    """Punto de entrada de la línea de comandos."""
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--benchmark", action="store_true")
    args = p.parse_args()
    datos = ruta_datos()
    if args.benchmark:
        print(benchmark(datos / "raw" / "csv", RAIZ / "reports"))
        return
    etapa = LimpiezaDask(datos / "raw" / "csv", datos / "processed")
    resultados = etapa.ejecutar_medido()
    print(f"{etapa} terminó en {etapa.segundos:.1f} s")
    for nombre, tabla in resultados.items():
        print(f"\n== {nombre}\n{tabla}")


if __name__ == "__main__":
    main()
