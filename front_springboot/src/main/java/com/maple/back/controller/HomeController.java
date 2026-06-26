package com.maple.back.controller;

import com.maple.back.model.Usuario;
import com.maple.back.services.auth.AuthenticationService;

import com.maple.back.services.password.PasswordResetService;

import com.maple.back.services.user.UsuarioService;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.*;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;

import org.springframework.web.servlet.mvc.support.RedirectAttributes;

import java.security.Principal;
import java.util.List;
@Controller
public class HomeController {

    private final UsuarioService usuarioService;

    private final AuthenticationService authenticationService;

    private final PasswordResetService passwordResetService;

    public HomeController(UsuarioService usuarioService,
                          AuthenticationService authenticationService,
                          PasswordResetService passwordResetService) {

        this.usuarioService = usuarioService;

        this.authenticationService = authenticationService;

        this.passwordResetService = passwordResetService;
    }

    // 🔹 Página principal (login)
    @GetMapping("/")
    public String rootRedirect(Authentication authentication) {
        return authenticationService.obtenerRedireccionSegunRol(authentication);
    }

    // 🔹 Procesar recuperación
    @PostMapping("/recover")
    public String procesarRecuperacion(@RequestParam String email,
                                       Model model) {

        boolean enviado = passwordResetService.generarToken(email);

        if (!enviado) {
            model.addAttribute("error",
                    "No existe una cuenta registrada con ese correo.");
            return "recuperar";
        }

        model.addAttribute("message",
                "Se ha enviado un enlace de recuperación.");
        return "recuperar";
    }
    @GetMapping("/recover")
    public String mostrarFormularioRecuperacion() {
        return "recuperar";
    }
    // 🔹 Mostrar formulario reset
    @GetMapping("/reset-password")
    public String mostrarFormularioReset(@RequestParam("token") String token,
                                         Model model) {

        boolean valido = passwordResetService.validarToken(token);

        if (!valido) {
            model.addAttribute("error", "Token inválido o expirado.");
            return "recuperar";
        }

        model.addAttribute("token", token);
        return "reset_password";
    }

    // 🔹 Procesar reset
    @PostMapping("/reset-password")
    public String procesarReset(@RequestParam String token,
                                @RequestParam String password,
                                @RequestParam String confirmPassword,
                                Model model) {

        if (!password.equals(confirmPassword)) {
            model.addAttribute("error", "Las contraseñas no coinciden.");
            model.addAttribute("token", token); // mantener token en el formulario
            return "reset_password";
        }

        boolean actualizado = passwordResetService.resetearPassword(token, password);

        if (!actualizado) {
            model.addAttribute("error", "Token inválido o expirado.");
            return "recuperar";
        }

        model.addAttribute("message", "Tu contraseña fue actualizada correctamente.");
        return "redirect:/";
    }


    // 🔹 Menú usuario
    @GetMapping("/menu")
    public String home(Model model,
                       Authentication authentication,
                       @RequestParam(defaultValue = "0") int page) {

        if (!authenticationService.estaAutenticado(authentication)) {
            return "redirect:/";
        }

        String email = authenticationService.obtenerEmailUsuario(authentication);
        Usuario usuario = usuarioService.obtenerPorEmail(email);



        model.addAttribute("usuario", usuario);


        return "menu";
    }

    // 🔹 Perfil usuario
    @GetMapping("/perfil")
    public String miPerfil(Model model, Authentication authentication) {

        if (!authenticationService.estaAutenticado(authentication)) {
            return "redirect:/";
        }

        String email = authenticationService.obtenerEmailUsuario(authentication);
        Usuario usuario = usuarioService.obtenerPorEmail(email);

        model.addAttribute("usuario", usuario);

        return "mi_perfil";
    }
    // 🔹 Completar datos del modal
    @PostMapping("/usuario/completar-datos")
    public String completarDatos(@ModelAttribute Usuario usuarioForm,
                                 Principal principal,
                                 RedirectAttributes redirectAttrs) {
        Usuario usuario = usuarioService.obtenerPorEmail(principal.getName());

        // Validación: todos los campos deben estar llenos
        if (usuarioForm.getCargo() == null || usuarioForm.getCargo().isBlank()
                || usuarioForm.getCedula() == null || usuarioForm.getCedula().isBlank()
                || usuarioForm.getPunto() == null || usuarioForm.getPunto().isBlank()
                || usuarioForm.getCiudad() == null || usuarioForm.getCiudad().isBlank()
                || usuarioForm.getTelefono() == null || usuarioForm.getTelefono().isBlank()) {

            redirectAttrs.addFlashAttribute("error", "Todos los campos son obligatorios.");
            return "redirect:/menu"; // vuelve a mostrar el modal
        }

        // Guardar datos usando el servicio
        usuarioService.actualizarDatosUsuario(usuario,
                usuarioForm.getCargo(),
                usuarioForm.getPunto(),
                usuarioForm.getCiudad(),
                usuarioForm.getCedula(),
                usuarioForm.getTelefono());

        return "redirect:/menu";
    }


}