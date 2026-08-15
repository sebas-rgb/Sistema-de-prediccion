package com.maple.back.dto;

import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

import java.time.LocalDate;
import java.util.List;

/**
 * DTOs del contrato con la API de prediccion (FastAPI).
 *
 * IMPORTANTE: se usa @JsonAlias y NO @JsonProperty.
 *
 *   @JsonProperty renombra en AMBAS direcciones: leeria "stock_actual" de
 *   Python, pero tambien lo ESCRIBIRIA asi hacia el navegador, y el JS espera
 *   camelCase.
 *
 *   @JsonAlias solo aplica al deserializar: acepta el snake_case que manda
 *   Python y sigue emitiendo camelCase (el nombre del componente del record).
 *
 * Tampoco se usa spring.jackson.property-naming-strategy=SNAKE_CASE: esa
 * propiedad es global y cambiaria el JSON de todos los demas endpoints.
 *
 * @JsonIgnoreProperties evita que un campo nuevo en Python rompa el deploy.
 * En Spring Boot 4 (Jackson 3) las anotaciones siguen en
 * com.fasterxml.jackson.annotation: ese paquete no cambio.
 */

public class InventarioDTO {

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Item(
            String codigo,
            LocalDate fecha,
            @JsonAlias("stock_actual") Double stockActual,
            String clase,
            @JsonAlias("consumo_promedio") Double consumoPromedio,
            @JsonAlias("probabilidad_agotamiento") Double probabilidadAgotamiento,
            @JsonAlias("nivel_riesgo") String nivelRiesgo
    ) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Pagina(
            LocalDate fecha,
            Integer total,
            Integer pagina,
            @JsonAlias("tamano_pagina") Integer tamanoPagina,
            @JsonAlias("version_modelo") String versionModelo,
            @JsonAlias("origen_modelo") String origenModelo,
            @JsonAlias("estado_validacion") String estadoValidacion,
            List<Item> items
    ) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record RangoFechas(
            @JsonAlias("primera_fecha") LocalDate primeraFecha,
            @JsonAlias("ultima_fecha") LocalDate ultimaFecha,
            @JsonAlias("dias_disponibles") Integer diasDisponibles
    ) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Salud(
            String status,
            @JsonAlias("model_loaded") Boolean modelLoaded
    ) {}
}