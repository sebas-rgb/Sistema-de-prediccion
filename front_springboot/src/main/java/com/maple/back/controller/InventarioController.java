package com.maple.back.controller;

import com.maple.back.dto.InventarioDTO;
import com.maple.back.services.prediction.PredictionClient;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDate;

/**
 * Proxy hacia la API de prediccion.
 *
 * El navegador NO llama a FastAPI directamente: pasa por aqui, de modo que
 * FastAPI puede quedarse en la red interna y la sesion de Spring sigue
 * protegiendo el acceso.
 */
@RestController
@RequestMapping("/api/inventario")
public class InventarioController {

    private final PredictionClient prediccion;

    public InventarioController(PredictionClient prediccion) {
        this.prediccion = prediccion;
    }

    @GetMapping("/fechas")
    public ResponseEntity<InventarioDTO.RangoFechas> fechas() {
        return prediccion.rangoFechas()
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).build());
    }

    @GetMapping("/sedes")
    public ResponseEntity<String> sedes() {
        return prediccion.reenviar(HttpMethod.GET, "/api/v1/inventario/sedes", null);
    }

    @GetMapping("/experimento")
    public ResponseEntity<InventarioDTO.Experimento> experimento() {
        return prediccion.experimento()
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).build());
    }

    /**
     * Proxy hacia el asistente. La API key del LLM vive en Python; ni Spring
     * ni el navegador la conocen.
     */
    @PostMapping("/asistente")
    public ResponseEntity<InventarioDTO.AsistenteRespuesta> asistente(
            @RequestBody InventarioDTO.AsistentePregunta pregunta) {

        if (pregunta == null || pregunta.pregunta() == null
                || pregunta.pregunta().isBlank()) {
            return ResponseEntity.badRequest().build();
        }
        return prediccion.preguntar(pregunta)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).build());
    }

    /**
     * Asistente en segundo plano: el navegador encola y luego pregunta "¿ya?".
     * Una sola peticion de un minuto se cortaba al cambiar de pagina.
     */
    @PostMapping("/asistente/tareas")
    public ResponseEntity<String> encolarPregunta(@RequestBody String pregunta) {
        return prediccion.reenviar(HttpMethod.POST, "/api/v1/asistente/tareas", pregunta);
    }

    @GetMapping("/asistente/tareas/{id}")
    public ResponseEntity<String> estadoPregunta(@PathVariable String id) {
        // El id se pega a la ruta hacia Python: solo se acepta un uuid en hex
        if (!id.matches("[0-9a-f]{32}")) {
            return ResponseEntity.badRequest().build();
        }
        return prediccion.reenviar(HttpMethod.GET, "/api/v1/asistente/tareas/" + id, null);
    }

    @GetMapping
    public ResponseEntity<InventarioDTO.Pagina> inventario(
            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate fecha,
            @RequestParam(required = false) String codigo,
            @RequestParam(required = false) String sede,
            @RequestParam(defaultValue = "1") int pagina,
            @RequestParam(defaultValue = "50") int tamanoPagina) {

        return prediccion.inventario(fecha, codigo, sede, pagina, tamanoPagina)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).build());
    }
}
