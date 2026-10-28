"""Esquemas Pydantic de los documentos que se guardan en MongoDB.

Validar en la aplicación evita documentos «sucios», como una calificación que a
veces llega como texto y a veces como número.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

PATRON_ESTUDIANTE = r"^E\d{7}$"


class Estado(str, Enum):
    """Estado de una tarea para un estudiante."""

    PENDIENTE = "pendiente"
    ENTREGADA = "entregada"
    TARDIA = "tardia"
    NO_ENTREGADA = "no_entregada"


class Modalidad(str, Enum):
    """Modalidades educativas admitidas (ver ``src/utils/calendario.py``)."""

    REGULAR = "regular"
    NOCTURNA = "nocturna"
    FIN_DE_SEMANA = "fin_de_semana"
    A_DISTANCIA = "a_distancia"


class Seguimiento(BaseModel):
    """Evento del historial de una tarea (cambio de estado)."""

    fecha: datetime
    estado: Estado
    nota: Optional[str] = Field(default=None, max_length=300)


class TareaDocumento(BaseModel):
    """Documento de la colección ``tareas``: una tarea asignada a un estudiante.

    Attributes:
        id_entrega: Identificador único de la tarea asignada.
        numero_estudiante: Código sintético ``E`` + 7 dígitos; es el único dato que pide la consulta.
        fecha_limite: Debe ser posterior o igual a ``fecha_asignacion``.
        calificacion: Entre 0 y 10, o None si aún no se califica.
        seguimiento: Historial semiestructurado de cambios de estado.
    """

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    id_entrega: str = Field(min_length=3, max_length=40)
    numero_estudiante: str = Field(pattern=PATRON_ESTUDIANTE)
    centro: str
    grado: str
    seccion: str = Field(max_length=2)
    modalidad: Modalidad
    materia: str
    tipo_tarea: str
    prioridad: str = Field(pattern=r"^(baja|media|alta)$")
    fecha_asignacion: datetime
    fecha_limite: datetime
    fecha_entrega: Optional[datetime] = None
    estado: Estado = Estado.PENDIENTE
    calificacion: Optional[float] = Field(default=None, ge=0, le=10)
    riesgo_tardia: Optional[float] = Field(default=None, ge=0, le=1)
    seguimiento: list[Seguimiento] = Field(default_factory=list)

    @model_validator(mode="after")
    def _fechas_coherentes(self) -> "TareaDocumento":
        if self.fecha_limite < self.fecha_asignacion:
            raise ValueError("fecha_limite no puede ser anterior a fecha_asignacion")
        if self.estado == Estado.PENDIENTE.value and self.fecha_entrega is not None:
            raise ValueError("una tarea pendiente no puede tener fecha_entrega")
        return self
