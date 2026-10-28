"""Generador determinista del dataset sintético de entregas de tareas.

Cada fila es una tarea asignada a un estudiante. El riesgo de entrega tardía
depende de reglas documentadas (modalidad, plazo, asuetos, tipo de tarea,
materia y una propensión latente del estudiante), así que el modelo tiene una
señal real que aprender. No hay ningún dato personal: el número de estudiante
es un código sintético.

Uso desde la terminal::

    python -m src.ingesta.generador --filas 10000000 --particiones 20
"""
from __future__ import annotations

import argparse
import os
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from src.utils.calendario import (ASUETOS_LOCALES_2026, CIERRE_ANIO_2026, INICIO_ANIO_2026,
                                  CalendarioEscolar)

#: Fecha de corte: las tareas que vencen después siguen pendientes.
FECHA_CORTE = date(2026, 10, 28)

DISTRITOS = ["San Salvador", "Santa Tecla", "Soyapango", "Mejicanos", "Apopa", "Santa Ana",
             "San Miguel", "Sonsonate", "Usulután", "La Libertad"]
GRADOS = ["1°", "2°", "3°", "4°", "5°", "6°", "7°", "8°", "9°", "1° bachillerato", "2° bachillerato"]
SECCIONES = ["A", "B", "C"]
MATERIAS = {"Matemática": 0.25, "Lenguaje": 0.05, "Ciencias": 0.10, "Sociales": 0.0,
            "Inglés": 0.15, "Educación Física": -0.40, "Artística": -0.20, "Informática": -0.05}
TIPOS = {"tarea": (0.0, [1, 2, 3]), "guía": (-0.2, [2, 3, 5]), "investigación": (0.2, [5, 7]),
         "laboratorio": (0.1, [3, 5]), "proyecto": (0.4, [7, 10])}
PRIORIDADES = {"baja": 0.1, "media": 0.0, "alta": -0.2}
MODALIDADES = {"regular": (0.78, 0.0), "nocturna": (0.09, 0.5),
               "fin_de_semana": (0.07, 0.3), "a_distancia": (0.06, 0.6)}
TURNO_POR_MODALIDAD = {"nocturna": "nocturno", "fin_de_semana": "fin de semana", "a_distancia": "virtual"}

COLUMNAS = ["id_entrega", "numero_estudiante", "centro", "distrito", "grado", "seccion", "modalidad",
            "turno", "materia", "docente", "tipo_tarea", "prioridad", "fecha_asignacion", "fecha_limite",
            "dias_plazo_habiles", "cruza_asueto", "fecha_entrega", "estado", "calificacion",
            "entrega_tardia"]


class GeneradorEntregas:
    """Genera particiones reproducibles del historial de entregas.

    Args:
        semilla: Semilla base; la partición ``i`` usa ``semilla + i``.
        tareas_por_estudiante: Tareas que recibe cada estudiante en el año.
        centros: Número de centros educativos simulados.
        proporcion_sucios: Fracción de filas con defectos inyectados (duplicados,
            calificaciones fuera de rango y texto mal escrito) para probar la limpieza.

    Example:
        >>> df = GeneradorEntregas(semilla=7).generar_particion(0, 1000)
        >>> len(df) >= 1000
        True
    """

    def __init__(self, semilla: int = 42, tareas_por_estudiante: int = 250, centros: int = 60,
                 proporcion_sucios: float = 0.002) -> None:
        self._semilla = semilla
        self._tareas = tareas_por_estudiante
        self._centros = centros
        self._sucios = proporcion_sucios
        self._dias, self._feriado_acum = self._precalcular_calendarios()

    def __repr__(self) -> str:
        return (f"GeneradorEntregas(semilla={self._semilla}, tareas_por_estudiante={self._tareas}, "
                f"centros={self._centros})")

    # ------------------------------------------------------------------ calendario
    @staticmethod
    def _precalcular_calendarios():
        """Días de clase por (modalidad, ¿distrito con asuetos locales?) y asuetos acumulados."""
        dias = {}
        for modalidad in MODALIDADES:
            for local in (False, True):
                distrito = next(iter(ASUETOS_LOCALES_2026)) if local else ""
                dias[(modalidad, local)] = CalendarioEscolar(distrito).dias_de_clase(modalidad)
        # Acumulado de días sin clases por asueto o vacaciones (sin contar fines de semana).
        cal = CalendarioEscolar()
        rango = np.arange(np.datetime64(INICIO_ANIO_2026), np.datetime64(CIERRE_ANIO_2026) + np.timedelta64(1, "D"))
        feriado = np.array([d.astype(object) in cal._sin_clases for d in rango], dtype=np.int32)
        return dias, np.cumsum(feriado)

    def _cruza_asueto(self, asignacion: np.ndarray, limite: np.ndarray) -> np.ndarray:
        """True si entre asignación y límite (sin incluirlos) hay asueto o vacaciones."""
        base = np.datetime64(INICIO_ANIO_2026)
        a = (asignacion - base).astype(int)
        b = (limite - base).astype(int)
        return (self._feriado_acum[np.maximum(b - 1, a)] - self._feriado_acum[a]) > 0

    # ------------------------------------------------------------------ generación
    def generar_particion(self, indice: int, filas: int) -> pd.DataFrame:
        """Genera una partición con aproximadamente ``filas`` tareas.

        Args:
            indice: Número de partición; fija la semilla y el rango de estudiantes.
            filas: Filas deseadas (se redondea a un múltiplo de ``tareas_por_estudiante``).

        Returns:
            DataFrame con las columnas de :data:`COLUMNAS`.
        """
        rng = np.random.default_rng(self._semilla + indice)
        n_est = max(1, round(filas / self._tareas))
        n = n_est * self._tareas

        # --- estudiantes
        id_est = indice * n_est + np.arange(n_est)
        centro_est = rng.integers(0, self._centros, n_est)
        distrito_centro = np.array(DISTRITOS)[np.arange(self._centros) % len(DISTRITOS)]
        nombres_mod = list(MODALIDADES)
        p_mod = np.array([v[0] for v in MODALIDADES.values()])
        mod_est = rng.choice(len(nombres_mod), n_est, p=p_mod / p_mod.sum())
        grado_est = rng.integers(0, len(GRADOS), n_est)
        seccion_est = rng.integers(0, len(SECCIONES), n_est)
        propension = rng.normal(0, 1, n_est)
        vespertino = rng.random(n_est) < 0.4

        e = np.repeat(np.arange(n_est), self._tareas)
        modalidad = np.array(nombres_mod)[mod_est][e]
        distrito = distrito_centro[centro_est][e]
        turno = np.where(vespertino, "vespertino", "matutino")[e].astype(object)
        for mod, nombre in TURNO_POR_MODALIDAD.items():
            turno[modalidad == mod] = nombre

        # --- tareas
        nombres_mat = list(MATERIAS)
        materia_i = rng.integers(0, len(nombres_mat), n)
        nombres_tipo = list(TIPOS)
        tipo_i = rng.choice(len(nombres_tipo), n, p=[0.40, 0.20, 0.15, 0.10, 0.15])
        prioridad_i = rng.choice(3, n, p=[0.3, 0.5, 0.2])
        plazo = np.empty(n, dtype=np.int16)
        for t, (_, opciones) in enumerate(TIPOS.values()):
            m = tipo_i == t
            plazo[m] = rng.choice(opciones, m.sum())

        asignacion = np.empty(n, dtype="datetime64[D]")
        limite = np.empty(n, dtype="datetime64[D]")
        local = distrito == "San Salvador"
        for (mod, es_local), dias in self._dias.items():
            m = (modalidad == mod) & (local == es_local)
            if not m.any():
                continue
            pos = rng.integers(0, len(dias) - 1, m.sum())
            asignacion[m] = dias[pos]
            limite[m] = dias[np.minimum(pos + plazo[m], len(dias) - 1)]
        cruza = self._cruza_asueto(asignacion, limite)

        # --- probabilidad de entrega tardía (reglas del generador)
        efecto_mod = np.array([v[1] for v in MODALIDADES.values()])[mod_est][e]
        logit = (-1.7 + 0.9 * propension[e] + efecto_mod
                 + np.array([v[0] for v in TIPOS.values()])[tipo_i]
                 + np.array(list(PRIORIDADES.values()))[prioridad_i]
                 + np.array(list(MATERIAS.values()))[materia_i]
                 + 0.5 * (plazo <= 2) + 0.35 * cruza
                 + 0.15 * (grado_est[e] >= 9) + 0.1 * (turno == "vespertino")
                 + 0.2 * (asignacion >= np.datetime64("2026-09-15"))
                 + rng.normal(0, 0.3, n))
        tardia = rng.random(n) < 1 / (1 + np.exp(-logit))
        no_entregada = tardia & (rng.random(n) < 0.3)

        adelanto = rng.integers(0, np.maximum(plazo, 1) + 1).astype("timedelta64[D]")
        atraso = rng.integers(1, 8, n).astype("timedelta64[D]")
        entrega = np.where(tardia, limite + atraso, limite - adelanto).astype("datetime64[D]")
        entrega = np.maximum(entrega, asignacion)

        pendiente = limite > np.datetime64(FECHA_CORTE)
        estado = np.where(no_entregada, "no_entregada", np.where(tardia, "tardia", "entregada")).astype(object)
        estado[pendiente] = "pendiente"

        nota = np.clip(rng.normal(7.6 - 0.6 * propension[e], 1.3) - 1.2 * tardia, 0, 10).round(1)
        nota[no_entregada] = 0.0

        df = pd.DataFrame({
            "id_entrega": [f"T{indice:03d}-{i:07d}" for i in range(n)],
            "numero_estudiante": pd.Series(id_est[e]).map("E{:07d}".format),
            "centro": pd.Series(centro_est[e]).map("C{:03d}".format),
            "distrito": distrito,
            "grado": np.array(GRADOS)[grado_est][e],
            "seccion": np.array(SECCIONES)[seccion_est][e],
            "modalidad": modalidad,
            "turno": turno,
            "materia": np.array(nombres_mat)[materia_i],
            "docente": [f"D{c:03d}{m}" for c, m in zip(centro_est[e], materia_i)],
            "tipo_tarea": np.array(nombres_tipo)[tipo_i],
            "prioridad": np.array(list(PRIORIDADES))[prioridad_i],
            "fecha_asignacion": asignacion.astype(str),
            "fecha_limite": limite.astype(str),
            "dias_plazo_habiles": plazo,
            "cruza_asueto": cruza,
            "fecha_entrega": np.where(no_entregada | pendiente, "", entrega.astype(str)),
            "estado": estado,
            "calificacion": np.where(pendiente, np.nan, nota),
            "entrega_tardia": np.where(pendiente, np.nan, tardia.astype(float)),
        })
        return self._ensuciar(df, rng)

    def _ensuciar(self, df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
        """Inyecta defectos realistas que la limpieza con Dask debe corregir."""
        if self._sucios <= 0:
            return df
        k = max(1, int(len(df) * self._sucios))
        filas = rng.choice(len(df), k, replace=False)
        df.loc[filas[: k // 3], "calificacion"] = 11.0                 # fuera de rango
        idx = filas[k // 3: 2 * k // 3]
        df.loc[idx, "materia"] = df.loc[idx, "materia"].str.upper() + " "  # texto inconsistente
        duplicados = df.iloc[filas[2 * k // 3:]]                       # filas repetidas
        return pd.concat([df, duplicados], ignore_index=True)

    def escribir(self, destino: Path, filas: int, particiones: int, formatos=("csv", "parquet")) -> dict:
        """Escribe el dataset completo en particiones CSV y Parquet.

        Args:
            destino: Carpeta ``data/raw``; se crean subcarpetas ``csv/`` y ``parquet/``.
            filas: Filas totales aproximadas.
            particiones: Número de archivos por formato.
            formatos: Formatos a escribir.

        Returns:
            Resumen con filas escritas y segundos empleados.
        """
        inicio = time.perf_counter()
        total = 0
        for fmt in formatos:
            (destino / fmt).mkdir(parents=True, exist_ok=True)
        for i in range(particiones):
            df = self.generar_particion(i, filas // particiones)
            total += len(df)
            if "csv" in formatos:
                df.to_csv(destino / "csv" / f"entregas_{i:03d}.csv", index=False)
            if "parquet" in formatos:
                df.to_parquet(destino / "parquet" / f"entregas_{i:03d}.parquet", index=False)
            print(f"  partición {i + 1}/{particiones}: {len(df):,} filas", flush=True)
        return {"filas": total, "segundos": round(time.perf_counter() - inicio, 1)}


def ruta_datos() -> Path:
    """Carpeta de datos: ``ATE_DATA_DIR`` si existe, si no ``data/`` del proyecto."""
    return Path(os.environ.get("ATE_DATA_DIR", Path(__file__).resolve().parents[2] / "data"))


def main() -> None:
    """Punto de entrada de la línea de comandos."""
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--filas", type=int, default=10_000_000)
    p.add_argument("--particiones", type=int, default=20)
    p.add_argument("--semilla", type=int, default=42)
    p.add_argument("--muestra", action="store_true", help="Escribe solo data/muestra/entregas_muestra.csv")
    args = p.parse_args()
    gen = GeneradorEntregas(semilla=args.semilla)
    if args.muestra:
        destino = Path(__file__).resolve().parents[2] / "data" / "muestra"
        gen.generar_particion(0, 5000).to_csv(destino / "entregas_muestra.csv", index=False)
        print("Muestra escrita en", destino)
        return
    print(gen, "->", ruta_datos() / "raw")
    print(gen.escribir(ruta_datos() / "raw", args.filas, args.particiones))


if __name__ == "__main__":
    main()
