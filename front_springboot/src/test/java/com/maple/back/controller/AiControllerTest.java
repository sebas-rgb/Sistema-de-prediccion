package com.maple.back.controller;

import com.maple.back.services.ai.OpenAiService;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import java.util.Map;

class AiControllerTest {

    @Test
    void devuelveRespuestaOpenAi() throws Exception {
        OpenAiService openAiService = Mockito.mock(OpenAiService.class);
        AiController controller = new AiController(openAiService);

        Mockito.when(openAiService.generarRespuesta("hola")).thenReturn("respuesta dinámica");

        ResponseEntity<Map<String, String>> response = controller.responder(new AiController.PreguntaRequest("hola"));

        org.junit.jupiter.api.Assertions.assertEquals(HttpStatus.OK, response.getStatusCode());
        org.junit.jupiter.api.Assertions.assertEquals("respuesta dinámica", response.getBody().get("respuesta"));
    }

    @Test
    void devuelveServicioNoDisponibleSiNoHayApiKey() throws Exception {
        OpenAiService openAiService = Mockito.mock(OpenAiService.class);
        AiController controller = new AiController(openAiService);

        Mockito.when(openAiService.generarRespuesta("hola"))
                .thenThrow(new IllegalStateException("No se configuró openai.api-key."));

        ResponseEntity<Map<String, String>> response = controller.responder(new AiController.PreguntaRequest("hola"));

        org.junit.jupiter.api.Assertions.assertEquals(HttpStatus.SERVICE_UNAVAILABLE, response.getStatusCode());
        org.junit.jupiter.api.Assertions.assertEquals("No se configuró openai.api-key.", response.getBody().get("error"));
    }
}
