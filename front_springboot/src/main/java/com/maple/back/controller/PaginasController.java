package com.maple.back.controller;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

/** Pantallas sin datos de servidor: todo lo cargan sus scripts por la API. */
@Controller
public class PaginasController {

    @GetMapping("/analisis")
    public String analisis() { return "analisis"; }

    @GetMapping("/simulador")
    public String simulador() { return "simulador"; }

    @GetMapping("/modelos")
    public String modelos() { return "modelos"; }
}
