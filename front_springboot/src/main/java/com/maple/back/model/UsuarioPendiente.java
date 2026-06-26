package com.maple.back.model;

import jakarta.persistence.*;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@Entity
@Table(name = "usuarios_pendientes")
@Data
@NoArgsConstructor
public class UsuarioPendiente {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Integer id;

    @Column(nullable = false)
    private String nombre;

    @Column(nullable = false, unique = true)
    private String email;

    @Column(nullable = false)
    private String contrasena;

    @Column(nullable = false, length = 12)
    private String cedula;

    @Column(nullable = false)
    private String telefono;

    @Column(nullable = false)
    private String ciudad;

    @Column
    private String punto;

    @Column
    private String cargo;

    @Column(nullable = false, unique = true, length = 100)
    private String token;

    @Column(nullable = false)
    private LocalDateTime expiracion;
}
