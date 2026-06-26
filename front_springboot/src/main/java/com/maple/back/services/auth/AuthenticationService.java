package com.maple.back.services.auth;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.stereotype.Service;

@Service
public class AuthenticationService {

    /**
     * Verifica si el usuario está autenticado
     */
    public boolean estaAutenticado(Authentication authentication) {
        return authentication != null &&
                !(authentication instanceof AnonymousAuthenticationToken);
    }

    /**
     * Verifica si el usuario tiene rol de administrador
     */
    public boolean esAdmin(Authentication authentication) {
        if (!estaAutenticado(authentication)) {
            return false;
        }
        return authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .anyMatch(role -> role.equals("ROLE_ADMIN"));
    }

    /**
     * Verifica si el usuario tiene rol de usuario normal
     */
    public boolean esUsuario(Authentication authentication) {
        if (!estaAutenticado(authentication)) {
            return false;
        }
        return authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .anyMatch(role -> role.equals("ROLE_USER"));
    }

    /**
     * Obtiene el email del usuario autenticado
     */
    public String obtenerEmailUsuario(Authentication authentication) {
        if (!estaAutenticado(authentication)) {
            throw new RuntimeException("Usuario no autenticado");
        }
        return authentication.getName();
    }

    /**
     * Redirige según el rol del usuario
     */
    public String obtenerRedireccionSegunRol(Authentication authentication) {
        if (!estaAutenticado(authentication)) {
            return "index";
        }

        if (esAdmin(authentication)) {
            return "redirect:/admin/tickets";
        }

        if (esUsuario(authentication)) {
            return "redirect:/menu";
        }

        return "index";
    }
}

