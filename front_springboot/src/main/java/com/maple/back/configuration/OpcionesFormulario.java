package com.maple.back.configuration;

import com.maple.back.services.auth.ValidationService;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.ModelAttribute;

import java.util.Set;
import java.util.TreeSet;

/**
 * Las opciones de ciudad, punto y cargo de los formularios salen de las listas
 * que valida el backend. Antes estaban copiadas a mano en cada plantilla y se
 * desincronizaron (el formulario ofrecía valores que luego se rechazaban).
 */
@ControllerAdvice
public class OpcionesFormulario {

    @ModelAttribute("ciudades")
    public Set<String> ciudades() { return new TreeSet<>(ValidationService.CIUDADES_VALIDAS); }

    @ModelAttribute("puntos")
    public Set<String> puntos() { return new TreeSet<>(ValidationService.PUNTOS_VALIDOS); }

    @ModelAttribute("cargos")
    public Set<String> cargos() { return new TreeSet<>(ValidationService.CARGOS_VALIDOS); }
}
