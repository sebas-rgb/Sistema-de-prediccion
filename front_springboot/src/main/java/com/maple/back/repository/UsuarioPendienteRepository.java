package com.maple.back.repository;

import com.maple.back.model.UsuarioPendiente;
import org.springframework.data.jpa.repository.JpaRepository;

import java.time.LocalDateTime;
import java.util.Optional;

public interface UsuarioPendienteRepository extends JpaRepository<UsuarioPendiente, Integer> {

    Optional<UsuarioPendiente> findByToken(String token);

    Optional<UsuarioPendiente> findByEmail(String email);

    Optional<UsuarioPendiente> findByCedula(String cedula);

    /** Borrar pendientes expirados (limpieza) */
    void deleteByExpiracionBefore(LocalDateTime fecha);
}

