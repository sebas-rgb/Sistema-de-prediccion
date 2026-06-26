package com.maple.back.model;

import jakarta.persistence.*;
import lombok.Data;
import com.fasterxml.jackson.annotation.JsonIgnore;

import java.util.List;

@Entity
@Table(name = "usuarios")
@Data
public class Usuario {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Integer id;

    @Column(nullable = false)
    private String nombre;

    @Column(nullable = false, unique = true)
    private String email;

    @Column(name = "contraseña", nullable = false)
    private String contrasena;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private Rol rol = Rol.USER;

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

    @Column(nullable = false)
    private boolean datosCompletos = false;
    

}
