package com.maple.back.controller;

import com.maple.back.services.ai.OpenAiService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestClientException;

import java.util.Map;

@RestController
@RequestMapping("/api/ia")
public class AiController {

    private final OpenAiService openAiService;

    public AiController(OpenAiService openAiService) {
        this.openAiService = openAiService;
    }

    @PostMapping({"/chat", "/responder"})
    public ResponseEntity<Map<String, String>> responder(@RequestBody PreguntaRequest request) {
        try {
            String respuesta = openAiService.generarRespuesta(request.mensaje());
            return ResponseEntity.ok(Map.of("respuesta", respuesta));
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        } catch (IllegalStateException e) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(Map.of("error", e.getMessage()));
        } catch (RestClientException e) {
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                    .body(Map.of("error", "No se pudo obtener respuesta de OpenAI."));
        }
    }

    public record PreguntaRequest(String mensaje) {
    }
}
