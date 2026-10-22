package com.maple.back.controller;

import com.maple.back.services.prediction.PredictionClient;

import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/** Proxy hacia /api/v1/pipeline: simular, extender, entrenar y comparar. */
@RestController
@RequestMapping("/api/pipeline")
public class PipelineController {

    private final PredictionClient prediccion;

    public PipelineController(PredictionClient prediccion) {
        this.prediccion = prediccion;
    }

    @GetMapping
    public ResponseEntity<String> estado() {
        return prediccion.reenviar(HttpMethod.GET, "/api/v1/pipeline", null);
    }

    @PostMapping("/tareas")
    public ResponseEntity<String> lanzar(@RequestBody String tarea) {
        return prediccion.reenviar(HttpMethod.POST, "/api/v1/pipeline/tareas", tarea);
    }
}
