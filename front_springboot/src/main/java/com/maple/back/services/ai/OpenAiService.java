package com.maple.back.services.ai;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

import java.util.List;
import java.util.Map;

@Service
public class OpenAiService {

    private final RestClient restClient;
    private final String apiKey;
    private final String model;

    public OpenAiService(@Value("${openai.api-key:}") String apiKey,
                         @Value("${openai.model:gpt-4o-mini}") String model,
                         @Value("${openai.api-url:https://api.openai.com/v1/chat/completions}") String apiUrl) {
        this.restClient = RestClient.builder().baseUrl(apiUrl).build();
        this.apiKey = apiKey;
        this.model = model;
    }

    public String generarRespuesta(String mensajeUsuario) {
        String pregunta = mensajeUsuario == null ? "" : mensajeUsuario.trim();
        if (pregunta.isEmpty()) {
            throw new IllegalArgumentException("El mensaje no puede estar vacío.");
        }
        if (apiKey == null || apiKey.isBlank()) {
            throw new IllegalStateException("No se configuró openai.api-key.");
        }

        OpenAiResponse response = restClient.post()
                .contentType(MediaType.APPLICATION_JSON)
                .header("Authorization", "Bearer " + apiKey)
                .body(Map.of(
                        "model", model,
                        "messages", List.of(Map.of("role", "user", "content", pregunta))
                ))
                .retrieve()
                .body(OpenAiResponse.class);

        if (response == null || response.choices == null || response.choices.isEmpty()
                || response.choices.get(0).message == null || response.choices.get(0).message.content == null
                || response.choices.get(0).message.content.isBlank()) {
            throw new IllegalStateException("OpenAI no devolvió contenido en la respuesta.");
        }
        return response.choices.get(0).message.content.trim();
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    private static class OpenAiResponse {
        public List<Choice> choices;
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    private static class Choice {
        public Message message;
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    private static class Message {
        public String content;
    }
}
