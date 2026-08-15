package com.maple.back.services.prediction;

import com.maple.back.dto.InventarioDTO;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

import java.time.Duration;
import java.time.LocalDate;
import java.util.Optional;

/**
 * Unico punto de contacto con la API de prediccion en Python.
 *
 * Notas de compatibilidad con Spring Boot 4:
 *  - Se construye el RestClient con RestClient.builder() en vez de inyectar un
 *    RestClient.Builder: en Boot 4 las autoconfiguraciones se dividieron en
 *    modulos y ese bean no siempre esta disponible.
 *  - Se capturan Exception y no solo RestClientException: en Jackson 3 los
 *    errores de deserializacion son unchecked (JacksonException extiende
 *    RuntimeException) y escapaban del catch anterior sin dejar rastro.
 */
@Service
public class PredictionClient {

    private static final Logger log = LoggerFactory.getLogger(PredictionClient.class);

    private final RestClient http;
    private final String baseUrl;

    public PredictionClient(
            @Value("${prediction.api.url:http://127.0.0.1:8000}") String baseUrl) {

        this.baseUrl = baseUrl;
        this.http = RestClient.builder()
                .baseUrl(baseUrl)
                .requestFactory(factoriaConTimeouts())
                .build();

        log.info("PredictionClient apuntando a {}", baseUrl);
    }

    /**
     * Sin timeouts, una FastAPI caida deja hilos de Tomcat colgados hasta
     * agotar el pool. Las sobrecargas con Duration son las vigentes: las de
     * int estan deprecadas desde Spring 6.1.
     */
    private static SimpleClientHttpRequestFactory factoriaConTimeouts() {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofSeconds(3));
        factory.setReadTimeout(Duration.ofSeconds(10));
        return factory;
    }

    /** true si la API responde y tiene el modelo cargado. */
    public boolean disponible() {
        try {
            InventarioDTO.Salud salud = http.get()
                    .uri("/health")
                    .retrieve()
                    // /health devuelve 503 cuando esta degradado: es una
                    // respuesta valida, no una excepcion.
                    .onStatus(HttpStatusCode::isError, (req, res) -> { })
                    .body(InventarioDTO.Salud.class);
            return salud != null && Boolean.TRUE.equals(salud.modelLoaded());
        } catch (Exception e) {
            log.warn("No se pudo consultar {}/health: {}", baseUrl, e.toString());
            return false;
        }
    }

    public Optional<InventarioDTO.RangoFechas> rangoFechas() {
        try {
            return Optional.ofNullable(http.get()
                    .uri("/api/v1/inventario/fechas")
                    .retrieve()
                    .body(InventarioDTO.RangoFechas.class));
        } catch (Exception e) {
            log.error("Fallo al obtener el rango de fechas desde {}", baseUrl, e);
            return Optional.empty();
        }
    }

    /** Comparacion de politicas de reposicion (resultado precalculado). */
    public Optional<InventarioDTO.Experimento> experimento() {
        try {
            return Optional.ofNullable(http.get()
                    .uri("/api/v1/experimento")
                    .retrieve()
                    .body(InventarioDTO.Experimento.class));
        } catch (Exception e) {
            log.error("Fallo al obtener el experimento desde {}", baseUrl, e);
            return Optional.empty();
        }
    }

    /**
     * Pagina de inventario con prediccion.
     *
     * @param fecha null = ultima fecha disponible
     */
    public Optional<InventarioDTO.Pagina> inventario(LocalDate fecha,
                                                     String codigo,
                                                     int pagina,
                                                     int tamanoPagina) {
        try {
            InventarioDTO.Pagina resultado = http.get()
                    .uri(uriBuilder -> {
                        uriBuilder.path("/api/v1/inventario")
                                .queryParam("pagina", pagina)
                                .queryParam("tamano_pagina", tamanoPagina);
                        if (fecha != null) {
                            uriBuilder.queryParam("fecha", fecha);
                        }
                        if (codigo != null && !codigo.isBlank()) {
                            uriBuilder.queryParam("codigo", codigo);
                        }
                        return uriBuilder.build();
                    })
                    .retrieve()
                    .body(InventarioDTO.Pagina.class);

            if (resultado == null) {
                log.warn("La API devolvio un cuerpo vacio para inventario");
                return Optional.empty();
            }

            log.debug("Inventario {} | {} items de {}",
                    resultado.fecha(), resultado.items().size(), resultado.total());
            return Optional.of(resultado);

        } catch (Exception e) {
            // Stack trace completo: aqui es donde aparecera la causa real
            // (conexion rechazada, JSON que no mapea, tipo incompatible...).
            log.error("Fallo al obtener inventario desde {}", baseUrl, e);
            return Optional.empty();
        }
    }
}
