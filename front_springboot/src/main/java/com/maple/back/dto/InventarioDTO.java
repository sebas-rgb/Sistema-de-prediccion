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

    // -----------------------------------------------------------
    // Comparacion de politicas de reposicion
    // -----------------------------------------------------------

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Politica(
            String politica,
            String etiqueta,
            @JsonAlias("dias_agotado") Integer diasAgotado,
            @JsonAlias("dias_agotado_utiles") Integer diasAgotadoUtiles,
            @JsonAlias("unidades_no_servidas") Integer unidadesNoServidas,
            @JsonAlias("fill_rate") Double fillRate,
            Integer pedidos,
            @JsonAlias("stock_promedio") Double stockPromedio,
            @JsonAlias("mejora_servicio_pct") Double mejoraServicioPct,
            @JsonAlias("serie_agotados") List<Integer> serieAgotados
    ) {}

    // -----------------------------------------------------------
    // Asistente
    // -----------------------------------------------------------

    /** Pregunta del usuario. No lleva la API key: esa vive solo en Python. */
    public record AsistentePregunta(String pregunta, LocalDate fecha) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record AsistenteRespuesta(
            String respuesta,
            @JsonAlias("fecha_contexto") LocalDate fechaContexto,
            @JsonAlias("modelo_llm") String modeloLlm,
            @JsonAlias("version_modelo_prediccion") String versionModeloPrediccion,
            @JsonAlias("origen_modelo") String origenModelo,
            @JsonAlias("estado_validacion") String estadoValidacion,
            @JsonAlias("herramientas_usadas") List<String> herramientasUsadas,
            @JsonAlias("tokens_entrada") Integer tokensEntrada,
            @JsonAlias("tokens_salida") Integer tokensSalida
    ) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Experimento(
            String generado,
            Integer dias,
            @JsonAlias("lead_time_dias") Integer leadTimeDias,
            Integer productos,
            @JsonAlias("fecha_inicio") LocalDate fechaInicio,
            @JsonAlias("version_modelo") String versionModelo,
            @JsonAlias("origen_modelo") String origenModelo,
            @JsonAlias("estado_validacion") String estadoValidacion,
            List<LocalDate> fechas,
            List<Politica> politicas
    ) {}
}
