"""Contrato HTTP. Estos schemas son lo que Spring Boot mapeara a DTOs.

Regla: nombres de campo estables, tipos predecibles, nada dinamico. Ningun
endpoint devuelve un DataFrame serializado.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from inventory_ml.config import MAX_BATCH_SIZE
from inventory_ml.features import CLASES

ClaseProducto = Literal["Muerto", "Baja", "Media", "Alta"]
NivelRiesgo = Literal["ALTO", "MEDIO", "BAJO"]

EJEMPLO_PRODUCTO = {
    "codigo": "188486",
    "stock_actual": 12,
    "consumo_promedio": 4.5,
    "consumo_minimo": 1,
    "consumo_maximo": 18,
    "reposicion_promedio": 120,
    "frecuencia_movimiento": 0.42,
    "clase": "Alta",
}


class ProductoRequest(BaseModel):
    """Estado actual de un producto. Campos de negocio, no columnas internas."""

    model_config = ConfigDict(json_schema_extra={"example": EJEMPLO_PRODUCTO})

    codigo: str = Field(..., min_length=1, max_length=64, description="Codigo del producto")
    stock_actual: float = Field(..., ge=0, description="Unidades disponibles hoy")
    consumo_promedio: float = Field(..., ge=0, description="Unidades consumidas por movimiento")
    consumo_minimo: float = Field(..., ge=0)
    consumo_maximo: float = Field(..., ge=0)
    reposicion_promedio: float = Field(..., ge=0, description="Tamano tipico de reposicion")
    frecuencia_movimiento: float = Field(
        ..., ge=0, le=1, description="Fraccion de dias con movimiento (0 a 1)"
    )
    clase: ClaseProducto = Field(..., description=f"Una de: {', '.join(CLASES)}")


class PrediccionResponse(BaseModel):
    """Probabilidad de agotamiento y su interpretacion."""

    codigo: str
    probabilidad_agotamiento: float = Field(..., ge=0, le=1)
    nivel_riesgo: NivelRiesgo
    horizonte_dias: int
    version_modelo: str | None
    fecha_prediccion: date
    origen_modelo: str | None = Field(
        None, description="SIMULADO mientras el modelo no se entrene con historia real"
    )
    estado_validacion: str | None = Field(
        None, description="NO_VALIDADO_CON_DATOS_REALES hasta validacion temporal real"
    )


class BatchRequest(BaseModel):
    """Varios productos en una sola llamada; se resuelven de forma vectorizada."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"items": [EJEMPLO_PRODUCTO]}}
    )

    items: list[ProductoRequest] = Field(
        ...,
        min_length=1,
        max_length=MAX_BATCH_SIZE,
        description=f"Entre 1 y {MAX_BATCH_SIZE} productos",
    )


class BatchResponse(BaseModel):
    total: int = Field(..., description="Cantidad de predicciones devueltas")
    resultados: list[PrediccionResponse]


class ModelInfoResponse(BaseModel):
    """Que modelo esta cargado. No expone rutas ni configuracion interna."""

    version_modelo: str | None
    algoritmo: str | None
    horizonte_dias: int | None
    origen_datos: str | None
    estado_validacion: str | None
    fecha_entrenamiento: str | None
    features_requeridas: list[str]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    model_loaded: bool


class ErrorResponse(BaseModel):
    detail: str


# ---------------------------------------------------------------
# Estado del inventario (lo que consume la tabla de Spring Boot)
# ---------------------------------------------------------------


class RangoFechasResponse(BaseModel):
    """Ventana temporal disponible en el inventario simulado."""

    primera_fecha: date
    ultima_fecha: date
    dias_disponibles: int


class InventarioItem(BaseModel):
    """Estado de un producto en una fecha, con su prediccion.

    NO incluye `agotado_30d`: esa es la etiqueta real y solo se conoce 30 dias
    despues. Mostrarla en una vista del dia actual seria mostrar el futuro.
    """

    codigo: str
    fecha: date
    stock_actual: float
    clase: ClaseProducto
    consumo_promedio: float
    probabilidad_agotamiento: float = Field(..., ge=0, le=1)
    nivel_riesgo: NivelRiesgo


class InventarioResponse(BaseModel):
    fecha: date = Field(..., description="Fecha efectiva del snapshot")
    total: int = Field(..., description="Productos que cumplen el filtro")
    pagina: int
    tamano_pagina: int
    version_modelo: str | None
    origen_modelo: str | None
    estado_validacion: str | None
    items: list[InventarioItem]


# ---------------------------------------------------------------
# Comparacion de politicas de reposicion
# ---------------------------------------------------------------


class PoliticaResultado(BaseModel):
    """Metricas de una politica de compra sobre la demanda simulada."""

    politica: str
    etiqueta: str = Field(..., description="Nombre legible para la interfaz")
    dias_agotado: int
    dias_agotado_utiles: int = Field(
        ..., description="Solo productos con demanda; los muertos en cero no cuentan"
    )
    unidades_no_servidas: int
    fill_rate: float = Field(..., ge=0, le=1)
    pedidos: int
    stock_promedio: float = Field(..., description="Capital inmovilizado promedio")
    mejora_servicio_pct: float
    serie_agotados: list[int] = Field(..., description="Productos agotados por dia")
    serie_stock: list[int] = Field(..., description="Unidades en stock al cierre de cada dia")
    serie_vendido: list[int] = Field(..., description="Unidades entregadas cada dia")


class ExperimentoResponse(BaseModel):
    generado: str
    dias: int
    lead_time_dias: int
    productos: int
    fecha_inicio: date
    version_modelo: str | None
    origen_modelo: str | None
    estado_validacion: str | None
    fechas: list[date]
    politicas: list[PoliticaResultado]


# ---------------------------------------------------------------
# Asistente
# ---------------------------------------------------------------


class AsistenteRequest(BaseModel):
    """Pregunta en lenguaje natural sobre el inventario."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"pregunta": "¿Que productos debo priorizar esta semana?"}
        }
    )

    pregunta: str = Field(
        ..., min_length=3, max_length=1000, description="Pregunta del usuario"
    )
    fecha: date | None = Field(
        None, description="Fecha del inventario a analizar; por defecto la ultima"
    )


class AsistenteResponse(BaseModel):
    respuesta: str
    fecha_contexto: date = Field(..., description="Fecha del inventario analizado")
    modelo_llm: str = Field(..., description="Modelo de lenguaje que respondio")
    version_modelo_prediccion: str | None
    origen_modelo: str | None
    estado_validacion: str | None
    herramientas_usadas: list[str] = Field(
        default_factory=list,
        description="Herramientas que el agente invoco, en orden. Vacio si respondio directo",
    )
    tokens_entrada: int | None = None
    tokens_salida: int | None = None
