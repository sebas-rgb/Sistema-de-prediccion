package com.maple.back.services.auth;

import com.maple.back.dto.RegisterRequest;
import com.maple.back.model.Rol;
import com.maple.back.model.Usuario;
import com.maple.back.model.UsuarioPendiente;
import com.maple.back.repository.UsuarioRepository;
import com.maple.back.repository.UsuarioPendienteRepository;
import com.maple.back.services.email.EmailService;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Service
public class RegisterService {

    private final UsuarioRepository usuarioRepository;
    private final UsuarioPendienteRepository pendienteRepository;
    private final PasswordEncoder passwordEncoder;
    private final ValidationService validationService;
    private final EmailService emailService;

    public RegisterService(UsuarioRepository usuarioRepository,
                           UsuarioPendienteRepository pendienteRepository,
                           PasswordEncoder passwordEncoder,
                           ValidationService validationService,
                           EmailService emailService) {
        this.usuarioRepository = usuarioRepository;
        this.pendienteRepository = pendienteRepository;
        this.passwordEncoder = passwordEncoder;
        this.validationService = validationService;
        this.emailService = emailService;
    }

    /**
     * Registra un nuevo usuario usando DTO
     */
    @Transactional
    public List<String> registerUser(RegisterRequest request) {
        normalize(request);
        return registrarPendiente(request);
    }

    /**
     * Registra un nuevo usuario como PENDIENTE y envía email de verificación
     */
    @Transactional
    public List<String> registerUser(
            String nombre,
            String email,
            String password,
            String confirmPassword,
            String cedula,
            String telefono,
            String ciudad,
            String punto,
            String cargo
    ) {
        RegisterRequest request = new RegisterRequest(
            nombre, email, password, confirmPassword, cedula, telefono, ciudad, punto, cargo
        );
        normalize(request);
        return registrarPendiente(request);
    }

    private List<String> registrarPendiente(RegisterRequest request) {
        // Validar campos
        List<String> errores = validarRequest(request);
        if (!errores.isEmpty()) {
            return errores;
        }

        pendienteRepository.findByEmail(request.getEmail()).ifPresent(pendienteRepository::delete);

        // Crear usuario pendiente con token
        String token = UUID.randomUUID().toString();

        UsuarioPendiente pendiente = new UsuarioPendiente();
        pendiente.setNombre(request.getNombre());
        pendiente.setEmail(request.getEmail());
        pendiente.setContrasena(passwordEncoder.encode(request.getPassword()));
        pendiente.setCedula(request.getCedula());
        pendiente.setTelefono(request.getTelefono());
        pendiente.setCiudad(request.getCiudad());
        pendiente.setPunto(request.getPunto());
        pendiente.setCargo(request.getCargo());
        pendiente.setToken(token);
        pendiente.setExpiracion(LocalDateTime.now().plusHours(24));

        pendienteRepository.save(pendiente);

        // Enviar email de verificación
        emailService.enviarVerificacionCuenta(request.getEmail(), request.getNombre(), token);

        return List.of();
    }

    private List<String> validarRequest(RegisterRequest request) {
        List<String> errores = new ArrayList<>(validationService.validarRegistro(
            request.getNombre(),
            request.getEmail(),
            request.getPassword(),
            request.getConfirmPassword(),
            request.getCedula(),
            request.getTelefono(),
            request.getCiudad(),
            request.getPunto(),
            request.getCargo()
        ));

        if (!errores.isEmpty()) {
            return errores;
        }

        if (usuarioRepository.findByEmail(request.getEmail()).isPresent()) {
            errores.add("El email ya está registrado");
        }

        if (usuarioRepository.findByCedula(request.getCedula()).isPresent()) {
            errores.add("La cédula ya está registrada");
        }

        pendienteRepository.findByEmail(request.getEmail())
            .filter(pendiente -> pendiente.getExpiracion().isAfter(LocalDateTime.now()))
            .filter(pendiente -> !pendiente.getCedula().equals(request.getCedula()))
            .ifPresent(pendiente -> errores.add("Ya existe un registro pendiente con este email"));

        pendienteRepository.findByCedula(request.getCedula())
            .filter(pendiente -> pendiente.getExpiracion().isAfter(LocalDateTime.now()))
            .filter(pendiente -> !pendiente.getEmail().equals(request.getEmail()))
            .ifPresent(pendiente -> errores.add("Ya existe un registro pendiente con esta cédula"));

        return errores;
    }

    private void normalize(RegisterRequest request) {
        request.setNombre(normalizeSpaces(request.getNombre()));
        request.setEmail(request.getEmail() == null ? null : request.getEmail().trim().toLowerCase());
        request.setCedula(request.getCedula() == null ? null : request.getCedula().trim());
        request.setTelefono(request.getTelefono() == null ? null : request.getTelefono().trim());
        request.setCiudad(request.getCiudad() == null ? null : request.getCiudad().trim().toUpperCase());
        request.setPunto(request.getPunto() == null ? null : request.getPunto().trim().toUpperCase());
        request.setCargo(request.getCargo() == null ? null : request.getCargo().trim().toUpperCase());
    }

    private String normalizeSpaces(String value) {
        return value == null ? null : value.trim().replaceAll("\\s+", " ");
    }

    /**
     * Verifica el token y activa la cuenta
     */
    public Optional<String> verificarCuenta(String token) {
        Optional<UsuarioPendiente> opt = pendienteRepository.findByToken(token);

        if (opt.isEmpty()) {
            return Optional.of("Token invalido o ya fue utilizado.");
        }

        UsuarioPendiente pendiente = opt.get();

        // Verificar expiración
        if (pendiente.getExpiracion().isBefore(LocalDateTime.now())) {
            pendienteRepository.delete(pendiente);
            return Optional.of("El enlace de verificacion ha expirado. Registrate nuevamente.");
        }

        // Verificar que no se haya registrado mientras tanto
        if (usuarioRepository.findByEmail(pendiente.getEmail()).isPresent()) {
            pendienteRepository.delete(pendiente);
            return Optional.of("Esta cuenta ya fue activada.");
        }

        // Crear usuario real
        Usuario usuario = new Usuario();
        usuario.setNombre(pendiente.getNombre());
        usuario.setEmail(pendiente.getEmail());
        usuario.setContrasena(pendiente.getContrasena());
        usuario.setCedula(pendiente.getCedula());
        usuario.setTelefono(pendiente.getTelefono());
        usuario.setCiudad(pendiente.getCiudad());
        usuario.setPunto(pendiente.getPunto());
        usuario.setCargo(pendiente.getCargo());
        usuario.setRol(Rol.USER);
        usuario.setDatosCompletos(true);

        usuarioRepository.save(usuario);

        // Borrar pendiente
        pendienteRepository.delete(pendiente);

        return Optional.empty();
    }

    /**
     * Verifica si un email ya está registrado
     */
    public boolean emailYaRegistrado(String email) {
        email = email == null ? null : email.trim().toLowerCase();
        return usuarioRepository.findByEmail(email).isPresent()
                || pendienteRepository.findByEmail(email).isPresent();
    }
}
