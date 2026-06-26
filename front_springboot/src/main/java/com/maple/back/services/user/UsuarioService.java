package com.maple.back.services.user;

import com.maple.back.model.Usuario;
import com.maple.back.repository.UsuarioRepository;
import org.springframework.stereotype.Service;

@Service
public class UsuarioService {

    private final UsuarioRepository usuarioRepository;

    public UsuarioService(UsuarioRepository usuarioRepository) {
        this.usuarioRepository = usuarioRepository;
    }

    /**
     * Obtiene un usuario por su email
     */
    public Usuario obtenerPorEmail(String email) {
        return usuarioRepository.findByEmail(email)
                .orElseThrow(() -> new RuntimeException("Usuario no encontrado"));
    }

    /**
     * Verifica si un usuario existe por email
     */
    public boolean existePorEmail(String email) {
        return usuarioRepository.findByEmail(email).isPresent();
    }

    /**
     * Guarda o actualiza un usuario
     */
    public Usuario guardar(Usuario usuario) {
        return usuarioRepository.save(usuario);
    }

    /**
     * Actualiza los datos obligatorios del modal
     */
    public Usuario actualizarDatosUsuario(Usuario usuario,
                                          String cargo,
                                          String punto,
                                          String ciudad,
                                          String cedula,
                                          String telefono) {
        usuario.setCargo(cargo);
        usuario.setPunto(punto);
        usuario.setCiudad(ciudad);
        usuario.setCedula(cedula);
        usuario.setTelefono(telefono);

        // ✅ Solo marcar como completo si todos los campos tienen valor
        boolean completos = cargo != null && !cargo.isBlank()
                && punto != null && !punto.isBlank()
                && ciudad != null && !ciudad.isBlank()
                && cedula != null && !cedula.isBlank()
                && telefono != null && !telefono.isBlank();

        usuario.setDatosCompletos(completos);

        return usuarioRepository.save(usuario);
    }
}
