package com.maple.back.services.password;

import com.maple.back.model.PasswordResetToken;
import com.maple.back.model.Usuario;
import com.maple.back.repository.PasswordResetTokenRepository;
import com.maple.back.repository.UsuarioRepository;
import com.maple.back.services.email.EmailService;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.UUID;

@Service
public class PasswordResetService {

    private final PasswordResetTokenRepository tokenRepository;
    private final UsuarioRepository usuarioRepository;
    private final PasswordEncoder passwordEncoder;
    private final EmailService emailService;

    public PasswordResetService(
            PasswordResetTokenRepository tokenRepository,
            UsuarioRepository usuarioRepository,
            PasswordEncoder passwordEncoder,
            EmailService emailService) {
        this.tokenRepository = tokenRepository;
        this.usuarioRepository = usuarioRepository;
        this.passwordEncoder = passwordEncoder;
        this.emailService = emailService;
    }

    // 🔹 Generar token y enviar correo
    @Transactional
    public boolean generarToken(String email) {
        var usuarioOpt = usuarioRepository.findByEmail(email);

        if (usuarioOpt.isEmpty()) {
            return false;
        }

        Usuario usuario = usuarioOpt.get();

        // Elimina tokens anteriores
        tokenRepository.deleteByUsuarioId(usuario.getId());

        String token = UUID.randomUUID().toString();

        PasswordResetToken resetToken = new PasswordResetToken();
        resetToken.setToken(token);
        resetToken.setUsuario(usuario);
        resetToken.setExpiracion(LocalDateTime.now().plusMinutes(30));

        tokenRepository.save(resetToken);

        // Enviar correo con el enlace
        emailService.enviarRecuperacionPassword(
                usuario.getEmail(),
                usuario.getNombre(),
                token
        );

        return true;
    }

    // 🔹 Validar token
    public boolean validarToken(String token) {
        PasswordResetToken tokenObj = tokenRepository.findByToken(token);

        return tokenObj != null &&
                tokenObj.getExpiracion().isAfter(LocalDateTime.now());
    }

    // 🔹 Resetear contraseña
    @Transactional
    public boolean resetearPassword(String token, String nuevaPassword) {
        PasswordResetToken tokenObj = tokenRepository.findByToken(token);

        if (tokenObj == null ||
                tokenObj.getExpiracion().isBefore(LocalDateTime.now())) {
            return false;
        }

        Usuario usuario = tokenObj.getUsuario();
        usuario.setContrasena(passwordEncoder.encode(nuevaPassword));
        usuarioRepository.save(usuario);

        // Eliminar token usado
        tokenRepository.delete(tokenObj);

        return true;
    }
}
