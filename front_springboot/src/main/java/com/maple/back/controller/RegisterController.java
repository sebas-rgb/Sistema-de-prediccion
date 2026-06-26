package com.maple.back.controller;

import com.maple.back.dto.RegisterRequest;
import com.maple.back.services.auth.RegisterService;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

import java.util.List;
import java.util.Optional;

@Controller
public class RegisterController {

    private final RegisterService registerService;

    public RegisterController(RegisterService registerService) {
        this.registerService = registerService;
    }

    @GetMapping("/register")
    public String showRegisterForm(Model model) {
        model.addAttribute("registerRequest", new RegisterRequest());
        return "register";
    }

    @PostMapping("/register")
    public String registerUser(
            @ModelAttribute RegisterRequest request,
            Model model,
            RedirectAttributes redirectAttributes
    ) {
        List<String> errores = registerService.registerUser(request);

        if (!errores.isEmpty()) {
            model.addAttribute("errores", errores);
            model.addAttribute("registerRequest", request);
            return "register";
        }

        redirectAttributes.addFlashAttribute("success",
            "Te enviamos un correo de verificacion. Revisa tu bandeja de entrada para activar tu cuenta.");
        return "redirect:/";
    }

    /** Endpoint donde llega el usuario al hacer click en el link del correo */
    @GetMapping("/verificar")
    public String verificarCuenta(@RequestParam String token, RedirectAttributes redirectAttributes) {

        Optional<String> error = registerService.verificarCuenta(token);

        if (error.isPresent()) {
            redirectAttributes.addFlashAttribute("error", error.get());
            return "redirect:/";
        }

        redirectAttributes.addFlashAttribute("success",
            "Tu cuenta ha sido verificada exitosamente. Ya puedes iniciar sesion.");
        return "redirect:/";
    }

    @GetMapping("/register/check-email")
    @ResponseBody
    public boolean checkEmail(@RequestParam String email) {
        return !registerService.emailYaRegistrado(email);
    }
}
